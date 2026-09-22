# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Website EU Emblem",
    "summary": "EU emblem in every header and the FEDER / NextGenerationEU funding strip in every footer",
    "version": "19.0.1.5.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Website",
    "license": "AGPL-3",
    "depends": ["website", "website_sale"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/website_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_eu_emblem/static/src/css/eu_emblem.css",
            "website_eu_emblem/static/src/scss/funding_footer.scss",
        ],
    },
    "installable": True,
}
