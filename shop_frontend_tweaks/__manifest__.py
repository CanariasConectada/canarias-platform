# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Shop Frontend Tweaks",
    "version": "19.0.1.0.0",
    "category": "Website/Website",
    "summary": "Shop visual tweaks: header, toolbar and searchable categories",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "LGPL-3",
    "depends": [
        "website",
        "website_sale",
    ],
    "data": [
        "views/shop_header.xml",
        "views/shop_toolbar.xml",
        "views/shop_searchable.xml",
        "views/shop_styles.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "shop_frontend_tweaks/static/src/css/remove_shadows.css",
            "shop_frontend_tweaks/static/src/css/ajax_loading.css",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
