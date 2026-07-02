# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Business Category Hierarchy",
    "version": "19.0.2.0.0",
    "category": "Contacts",
    "summary": "Hierarchical business categories to segment companies",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["MikeColangelo"],
    "development_status": "Production/Stable",
    "depends": [
        "contacts",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/business_category_views.xml",
        "views/res_company_views.xml",
        "wizard/import_categories_views.xml",
    ],
    "demo": [
        "demo/business_category_demo.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
