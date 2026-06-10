# Copyright 2026 Tu Empresa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Business Category Hierarchy",
    "version": "19.0.1.3.0",
    "category": "Sales/CRM",
    "summary": "Gestión jerárquica de categorías de comercio para segmentación de empresas",
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
    "license": "AGPL-3",
    "depends": [
        "contacts",
        "zones_company",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/business_category_views.xml",
        "views/res_company_views.xml",
        "wizard/import_categories_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
