# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Website EU Emblem",
    "summary": "Show the European Union emblem and its funding statement in the header",
    "version": "19.0.1.3.0",
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
        ],
    },
    "installable": True,
}
