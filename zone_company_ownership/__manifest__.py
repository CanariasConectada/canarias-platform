# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Zone Company Ownership",
    "summary": "A merchant's products and users also belong to their zone company",
    "version": "19.0.1.0.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Multi Company",
    "license": "AGPL-3",
    "depends": [
        "res_company_zone",
        "product_multi_company",
    ],
    "data": [
        "views/res_company_views.xml",
    ],
    "installable": True,
}
