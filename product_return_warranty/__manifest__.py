# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Product Return Warranty",
    "version": "19.0.2.0.1",
    "category": "Website/Website",
    "summary": "Per-product return warranty and delivery time on the shop page",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "LGPL-3",
    "depends": [
        "product",
        "website_sale",
    ],
    "data": [
        "views/product_template_views.xml",
        "views/website_sale_product_page.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
