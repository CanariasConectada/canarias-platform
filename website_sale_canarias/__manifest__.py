# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Sale Canarias Design",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "The Canarias Conectada shop look: hero header, searchable "
    "category sidebar, merchant badge on every card and AJAX filtering",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Production/Stable",
    "depends": [
        # is_marketplace / marketplace_zone and the aggregated-shop domain
        # this design renders on top of.
        "website_sale_marketplace",
        # The .wd-select CSS this module's category dropdown reuses, so the
        # shop and the directory share one visual language.
        "website_directory",
        # Ships the generic "Tienda <website>" hero every microsite keeps;
        # this module silences it on the aggregated shops, where the
        # Canarias/zone hero replaces it (see shop_hero_no_generic).
        "shop_frontend_tweaks",
    ],
    "data": [
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_canarias/static/src/css/website_sale_canarias.css",
            "website_sale_canarias/static/src/js/website_sale_canarias.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
