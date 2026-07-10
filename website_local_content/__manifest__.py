# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Local Content",
    "version": "19.0.1.2.0",
    "category": "Website",
    "summary": "Parameterizable local content galleries (places, memories, ...)",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website",
    ],
    "data": [
        "security/local_content_security.xml",
        "security/ir.model.access.csv",
        "security/local_content_rules.xml",
        "data/local_content_type_data.xml",
        "views/local_content_type_views.xml",
        "views/local_content_category_views.xml",
        "views/local_content_item_views.xml",
        "views/local_content_menus.xml",
        "views/website_local_content_templates.xml",
    ],
    "demo": [
        "demo/local_content_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_local_content/static/src/css/website_local_content.css",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
}
