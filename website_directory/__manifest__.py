# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Directory",
    "version": "19.0.7.3.0",
    "category": "Website",
    "summary": "Public business directory with category filter, search and shuffle",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Production/Stable",
    "depends": [
        "website",
        "res_company_category",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/website_directory_cron.xml",
        "views/website_directory_templates.xml",
        "views/res_company_views.xml",
    ],
    "demo": [
        "demo/website_directory_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_directory/static/src/css/website_directory.css",
            "website_directory/static/src/js/website_directory.js",
        ],
    },
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": True,
    "auto_install": False,
}
