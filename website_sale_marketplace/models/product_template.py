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
            # Command.link is idempotent, so re-linking an owner company is a
            # no-op.
            products.sudo().write(
                {"company_ids": [fields.Command.link(c.id) for c in companies]}
            )
        return products
