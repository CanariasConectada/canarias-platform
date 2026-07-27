# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

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
