# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from odoo.fields import Domain
from odoo.tools import split_every

_logger = logging.getLogger(__name__)

# Products to link per write during the marketplace backfill. One write per
# bounded batch of ids (identical vals) keeps the ORM cache/flush footprint
# flat regardless of catalog size, while producing the exact same end state
# as a single unbounded write.
BACKFILL_BATCH_SIZE = 1000


class Website(models.Model):
    _inherit = "website"

    is_marketplace = fields.Boolean(
        string="Marketplace",
        help="When enabled, this website's shop lists the published products of "
        "every company. It works by adding this website's company to each "
        "product's allowed companies, so the marketplace can see them while "
        "every other website keeps showing only its own company's products "
        "(product_multi_company isolation). Products still belong to their own "
        "merchant company; the marketplace company is only added as an extra "
        "visibility scope.",
    )

    marketplace_zone = fields.Selection(
        selection=lambda self: (
            self.env["res.company"]._fields["commercial_zone"].selection
            if "commercial_zone" in self.env["res.company"]._fields
            else []
        ),
        string="Zona del marketplace",
        help="Restrict this marketplace to the businesses of one commercial "
        "zone. Empty means the whole platform, which is what the main portal "
        "wants; the neighbourhood shops set their own zone.",
    )

    @api.model
    def _marketplace_companies(self):
        """Companies that own at least one marketplace website."""
        return self.sudo().search([("is_marketplace", "=", True)]).company_id

    def sale_product_domain(self):
        """Drop the per-website pin from the shop domain on a marketplace.

        ``website_sale`` builds the shop domain as
        ``sale_ok AND website_id in (False, this) AND company_id in (...)``.
        The ``website_id`` leaf is the same restriction the ``ir.rule`` on
        ``website_published`` applies (see ``product_template.py``), and it has
        to go for the same reason: a product a merchant pinned to their own
        site would otherwise never reach the marketplace, however many
        companies are allowed to see it.

        The leaf is rewritten to TRUE rather than the domain rebuilt from
        scratch, so every other condition core adds — now or in a future
        version — keeps applying untouched.
        """
        domain = super().sale_product_domain()
        website = self or self.get_current_website()
        if not website.is_marketplace:
            return domain
        domain = domain.map_conditions(
            lambda cond: Domain.TRUE if cond.field_expr == "website_id" else cond
        )
        # A zone marketplace is the same mechanism, narrowed: show the
        # products of the businesses in that neighbourhood. The three zone
        # shops listed nothing because no product was ever linked to a zone
        # company — and linking them would have been the wrong fix, since a
        # merchant belongs to a zone, not a product.
        zone_companies = website._zone_company_ids()
        if zone_companies:
            domain &= Domain("company_ids", "in", zone_companies)
        return domain

    @api.model
    def _zone_field_available(self):
        """True when res_company_zone is installed.

        Checked rather than depended on: the marketplace is useful without
        zones, and a hard dependency would drag the directory stack into any
        database that only wants the aggregated shop.
        """
        return "commercial_zone" in self.env["res.company"]._fields

    def _zone_company_ids(self):
        """Ids of the businesses in this website's zone, resolved as sudo.

        Written as an explicit id list instead of the obvious
        ``company_ids.commercial_zone = zone`` leaf because that dotted path
        walks into ``res.company``, where the shop's public user may only read
        its own company. The subquery came back empty and the zone shop listed
        nothing, with no error to explain why.
        """
        self.ensure_one()
        if not self.marketplace_zone or not self._zone_field_available():
            return []
        return (
            self.env["res.company"]
            .sudo()
            .search([("commercial_zone", "=", self.marketplace_zone)])
            .ids
        )

    def _sync_marketplace_products(self):
        """Ensure every product is visible to this record's marketplace
        companies by adding them to the product ``company_ids`` m2m.

        A product visible to companies ``[merchant, marketplace]`` shows on both
        the merchant site and the marketplace, but never on a *different*
        merchant's site (that company is not in ``company_ids``), so isolation
        between merchants is preserved.
        """
        Product = self.env["product.template"].sudo()
        # A ZONE marketplace is skipped on purpose. It does not need the link:
        # it selects products through their merchant's zone, and the isolation
        # rule reads product.company_id (empty on every product here), so
        # nothing is blocking those reads in the first place. Running the
        # backfill anyway would add three more companies to all 1576 products
        # and, worse, blow up: writing company_ids recomputes the delivery
        # carriers and website_sale_collect then refuses with "el método de
        # entrega y el almacén deben compartir la misma compañía", because 68
        # businesses have no pickup carrier of their own.
        for website in self.filtered(
            lambda w: w.is_marketplace and not w.marketplace_zone
        ):
            company = website.company_id
            # The many2many "not in" leaf compiles to a single SQL anti-join
            # (NOT EXISTS (SELECT 1 FROM product_company_rel ...)), so the
            # products already linked to the marketplace company are excluded
            # by PostgreSQL itself: the backfill only ever writes the missing
            # products (O(missing), not O(catalog)) and re-syncing an already
            # synced marketplace touches no product at all.
            #
            # Products with an EMPTY company_ids are global: visible to every
            # company (marketplace included), so there is nothing to add.
            # Linking the marketplace company to them would actually RESTRICT
            # them to the marketplace alone, hiding them from every other
            # website and tripping product_multi_company_stock's constraint
            # when another company holds stock for them. Skip them.
            #
            # Products whose owners are ALL archived are skipped too: an
            # archived business is out of the platform, and the aggregated
            # shop advertising its catalogue was exactly the bug reported on
            # 2026-08-10 — 283 products of retired merchants on the portal.
            # The zone shops never had it (they resolve companies through an
            # active-only search); this brings the portal in line.
            active_owner_ids = (
                self.env["res.company"]
                .sudo()
                .search([("id", "not in", self._marketplace_companies().ids)])
                .ids
            )
            missing_ids = Product.search(
                [
                    ("company_ids", "!=", False),
                    ("company_ids", "not in", company.ids),
                    ("company_ids", "in", active_owner_ids),
                ]
            ).ids
            vals = {"company_ids": [fields.Command.link(company.id)]}
            # Same vals for every product: write per bounded batch of ids and
            # flush each batch, instead of one unbounded write, so memory and
            # SQL statement size stay constant on large catalogs. The end
            # state is identical to a single global write.
            for batch_ids in split_every(BACKFILL_BATCH_SIZE, missing_ids):
                try:
                    Product.browse(batch_ids).write(vals)
                    Product.flush_model(["company_ids"])
                except Exception:
                    # Log-and-reraise: keep the abort-on-failure semantics but
                    # leave enough diagnostics to pinpoint the failing batch.
                    _logger.exception(
                        "Marketplace backfill failed on website %s (id %s), "
                        "company %s (id %s), batch of %s products "
                        "(first ids: %s)",
                        website.name,
                        website.id,
                        company.name,
                        company.id,
                        len(batch_ids),
                        batch_ids[:10],
                    )
                    raise
            _logger.info(
                "Marketplace backfill done for website %s (id %s), "
                "company %s (id %s): %s product(s) linked",
                website.name,
                website.id,
                company.name,
                company.id,
                len(missing_ids),
            )

    @api.model_create_multi
    def create(self, vals_list):
        websites = super().create(vals_list)
        websites._sync_marketplace_products()
        return websites

    def write(self, vals):
        res = super().write(vals)
        if {"is_marketplace", "company_id"} & set(vals):
            self._sync_marketplace_products()
        return res
