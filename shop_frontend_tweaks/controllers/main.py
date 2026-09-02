# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.fields import Domain

from odoo.addons.website_sale.controllers.main import WebsiteSale


class WebsiteSaleTwinCategories(WebsiteSale):
    def _get_shop_domain(
        self, search, category, attribute_value_dict, search_in_description=True
    ):
        """Filtering by a category means filtering by its visible name.

        The sidebar collapses same-named sibling categories into one entry
        (see ``product.public.category._shop_twin_categories``), so the
        entry the visitor clicked has to stand for all of them. The
        category leaf is therefore built here over the whole twin set
        instead of letting ``super()`` pin it to the one id that happened
        to represent the group.
        """
        domain = super()._get_shop_domain(
            search, None, attribute_value_dict, search_in_description
        )
        if category:
            twins = category._shop_twin_categories()
            domain &= Domain("public_categ_ids", "child_of", twins.ids)
        return domain
