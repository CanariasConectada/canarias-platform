# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _is_marketplace_context(self):
        """True when the website currently being rendered is a marketplace."""
        website_id = self.env.context.get("website_id")
        if not website_id:
            return False
        return bool(self.env["website"].sudo().browse(website_id).is_marketplace)

    @api.depends_context("website_id")
    def _compute_website_published(self):
        """On a marketplace, publication alone decides visibility.

        ``website.published.multi.mixin`` computes ``website_published`` as
        ``is_published AND website_id in (False, current_website)``. Widening
        ``company_ids`` — everything this module did until now — cannot survive
        that second condition: a merchant who pins a product to their own site
        hides it from the marketplace too. Pinning is the norm here, so the
        portal could only ever list the unpinned minority.

        Dropping the pin on a marketplace website is what makes the module's
        promise true. Merchant sites keep both conditions and stay isolated,
        and an unpublished product stays invisible everywhere.
        """
        if not self._is_marketplace_context():
            return super()._compute_website_published()
        for record in self:
            record.website_published = record.is_published

    def _search_company_id(self, operator, value):
        """Let a zone shop read the products of its own neighbourhood.

        The isolation rule is Odoo's global ``product_comp_rule``,
        ``company_id parent_of company_ids OR company_id = False``, and
        ``base_multi_company`` rewrites ``company_id`` searches onto the
        ``company_ids`` m2m. A zone shop's public user therefore only matches
        products already linked to the zone company — and none are: a product
        belongs to its merchant, not to a neighbourhood. The three zone shops
        listed zero of the 671 published products their own businesses have.

        Widening ``company_ids`` instead was tried and rejected: it writes on
        all 1576 products, and the write recomputes the delivery carriers,
        which ``website_sale_collect`` rejects because 68 businesses have no
        pickup carrier of their own.

        So the rule is left alone and the *translation* is extended, only:

        * on a website that is a zone marketplace, and
        * for a frontend visitor — an internal user's searches are untouched,
          so nothing changes in the backend.

        Merchant isolation survives: this adds the businesses of ONE
        neighbourhood on a website whose whole purpose is to list them, and a
        plain merchant microsite never enters this branch.
        """
        domain = super()._search_company_id(operator, value)
        if self.env.user._is_internal():
            return domain
        website_id = self.env.context.get("website_id")
        if not website_id:
            return domain
        website = self.env["website"].sudo().browse(website_id).exists()
        if not website or not website.is_marketplace:
            return domain
        zone_companies = website._zone_company_ids()
        if not zone_companies:
            return domain
        # Only the membership tests the isolation rule actually uses, and only
        # the positive ones — a negative test ("products NOT in these
        # companies") must stay exactly as strict as it was.
        #
        # ``=`` is deliberately NOT in the list, even though the rule's second
        # leaf is ``company_id = False``. Widening that one would make a
        # search for "products with no company" answer with the zone's
        # products, which is a lie about the data; and it buys nothing,
        # because the first leaf is already widened and the rule ORs them.
        if operator not in ("parent_of", "child_of", "in"):
            return domain
        return Domain.OR([domain, Domain("company_ids", "in", zone_companies)])

    def _search_website_published(self, operator, value):
        """Search counterpart of the compute above.

        This is the one that actually matters for the shop: the public user
        reads products through an ``ir.rule`` on ``website_published``, so the
        pin is applied in SQL long before ``sale_product_domain`` is consulted.
        """
        if (
            self._is_marketplace_context()
            and operator == "in"
            and list(value) == [True]
        ):
            return Domain("is_published", "=", True)
        return super()._search_website_published(operator, value)

    @api.model
    def _wsm_sweep_orphaned_marketplace_links(self):
        """Remove portal/zone marketplace links from products whose every
        active real owner is gone.

        Pure SQL on the m2m: writing ``company_ids`` through the ORM
        recomputes the delivery carriers, and the businesses without a pickup
        carrier of their own make that blow up — the same reason the backfill
        batches and the migration sweeps in SQL. The CTE is the one the
        19.0.1.4.0 post-migration and fix f30 use, promoted here so archiving
        a merchant cleans up after itself instead of needing a manual pass.
        """
        # The link this runs right after (the create-hook backfill, or the
        # archival that triggered it) may still be in the ORM cache; the raw
        # SQL reads the table, so flush first or it sweeps a stale snapshot.
        self.env["product.template"].flush_model(["company_ids"])
        self.env["res.company"].flush_model(["active"])
        self.env.cr.execute(
            """
            WITH marketplace AS (
                SELECT DISTINCT company_id FROM website WHERE is_marketplace
            ),
            doomed AS (
                SELECT r.product_template_id, r.res_company_id
                FROM product_template_res_company_rel r
                JOIN marketplace m ON m.company_id = r.res_company_id
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM product_template_res_company_rel r2
                    JOIN res_company c2 ON c2.id = r2.res_company_id
                    WHERE r2.product_template_id = r.product_template_id
                      AND c2.active
                      AND c2.id NOT IN (SELECT company_id FROM marketplace)
                )
            )
            DELETE FROM product_template_res_company_rel r
            USING doomed d
            WHERE r.product_template_id = d.product_template_id
              AND r.res_company_id = d.res_company_id
            """
        )
        if self.env.cr.rowcount:
            self.invalidate_model(["company_ids"])
            _logger.info(
                "Marketplace links swept from %s product(s) of retired "
                "merchants", self.env.cr.rowcount,
            )

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        # New products created by a merchant must also become visible on the
        # marketplace, so add the PORTAL marketplace company to their allowed
        # companies. Ownership is unchanged (the merchant company stays in
        # company_ids); the marketplace company is only an extra scope.
        #
        # Zone marketplace companies are excluded, exactly as the backfill
        # excludes them (_sync_marketplace_products): a zone shop selects its
        # products through the merchant's commercial_zone, never through a
        # link to the zone company. Linking every zone company here made a
        # new product of ONE neighbourhood visible in EVERY zone shop — the
        # public user of the Tamaraceite shop is allowed company 13, the
        # product carried 13 in company_ids, so the record rule passed
        # (confirmed 2026-08-11: a Guanarteme product surfaced in
        # Tamaraceite). It also risked the delivery-carrier recompute the
        # backfill batches around.
        companies = self.env["website"]._portal_marketplace_companies()
        if companies:
            # Only write on the products actually missing a marketplace
            # company (company_ids is already in cache right after create, so
            # this filter costs no extra SQL). Command.link is idempotent, but
            # the write itself is not free (write_date, recomputes), so skip
            # products created with every marketplace company already linked
            # — e.g. products created by the marketplace company itself.
            # Products created with an EMPTY company_ids are global (visible
            # everywhere, marketplace included); linking a company would
            # restrict them instead of widening them, so skip those too.
            missing = products.filtered(
                lambda product: product.company_ids and companies - product.company_ids
            )
            if missing:
                missing.sudo().write(
                    {"company_ids": [fields.Command.link(c.id) for c in companies]}
                )
        return products
