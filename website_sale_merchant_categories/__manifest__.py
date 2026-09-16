# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Sale Merchant Categories",
    "version": "19.0.1.1.0",
    "category": "Website/eCommerce",
    "summary": "Merchants curate the category tiles of their own shop: a "
    "per-site image for a shared category, and categories of their own",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": [
        # Renders the tile row above the shop grid and exposes the per-node
        # hook (`website._wsc_category_tile`) this module answers first.
        "website_sale_canarias",
        # The group that makes a user a merchant: the ACL rows and record
        # rules below are written for it.
        "merchant_group",
        # Which shop the caller owns (`res.company._get_editable_microsite_
        # companies`), the "My shops" list the screen hangs a button on, and
        # the ownership guard on a website row (`_pmm_assert_own_site`).
        "partner_microsite_manager",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/website_category_tile_views.xml",
        "views/product_public_category_views.xml",
        "views/website_views.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
