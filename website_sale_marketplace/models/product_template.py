# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.fields import Domain


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

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        # New products created by a merchant must also become visible on the
        # marketplace, so add every marketplace company to their allowed
        # companies. Ownership is unchanged (the merchant company stays in
        # company_ids); the marketplace company is only an extra scope.
        companies = self.env["website"]._marketplace_companies()
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
