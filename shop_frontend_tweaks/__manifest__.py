# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Shop Frontend Tweaks",
    "version": "19.0.3.2.0",
    "category": "Website/Website",
    "summary": "Shop tweaks: header, toolbar, searchable categories and "
    "recommended products",
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
        "views/product_recommended.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "shop_frontend_tweaks/static/src/css/shop_layout.css",
            "shop_frontend_tweaks/static/src/css/shop_toolbar.css",
            "shop_frontend_tweaks/static/src/css/searchable_categories.css",
            "shop_frontend_tweaks/static/src/js/shop_toolbar.js",
            "shop_frontend_tweaks/static/src/js/searchable_categories.js",
            "shop_frontend_tweaks/static/src/css/product_card.css",
            "shop_frontend_tweaks/static/src/css/recommended.css",
            "shop_frontend_tweaks/static/src/css/ajax_loading.css",
            "shop_frontend_tweaks/static/src/css/page_loader.css",
            "shop_frontend_tweaks/static/src/js/page_loader.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
