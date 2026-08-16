# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ProductPublicCategory(models.Model):
    _name = "product.public.category"
    _inherit = ["product.public.category", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        # Shop categories carry no company: the same tree is the navigation of
        # every website, so it is in scope as soon as the feature is on.
        return [
            "name",
            "website_description",
            "website_footer",
            "website_meta_title",
            "website_meta_description",
        ]
