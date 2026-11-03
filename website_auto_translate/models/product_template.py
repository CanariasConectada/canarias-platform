# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

TRANSLATED_FIELDS = [
    "name",
    "description_sale",
    "website_description",
    # The paragraph the product page itself renders. Separate from
    # ``website_description`` in Odoo 19, and left out until 19.0.3.0.0, so a
    # shop that wrote its copy there had it stay in Spanish in every language.
    "description_ecommerce",
]


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return TRANSLATED_FIELDS

    def _auto_translate_scoped(self):
        """Products belonging to a shop that opted into the rollout.

        A product with no company at all is platform-wide catalogue, so it
        rides along as soon as anybody is opted in.
        """
        enabled = self.env["res.company"]._auto_translate_companies()
        if not enabled:
            return self.browse()
        return self.sudo().filtered(
            lambda product: not product.company_ids or (product.company_ids & enabled)
        )
