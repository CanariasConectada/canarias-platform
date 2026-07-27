# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
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

    @api.model
    def _marketplace_companies(self):
        """Companies that own at least one marketplace website."""
        return self.sudo().search([("is_marketplace", "=", True)]).company_id

    def _sync_marketplace_products(self):
        """Ensure every product is visible to this record's marketplace
        companies by adding them to the product ``company_ids`` m2m.

        A product visible to companies ``[merchant, marketplace]`` shows on both
        the merchant site and the marketplace, but never on a *different*
        merchant's site (that company is not in ``company_ids``), so isolation
        between merchants is preserved.
        """
        Product = self.env["product.template"].sudo()
        for website in self.filtered("is_marketplace"):
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
            missing_ids = Product.search(
                [
                    ("company_ids", "!=", False),
                    ("company_ids", "not in", company.ids),
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
