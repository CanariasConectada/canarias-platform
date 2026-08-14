# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Zone Company Ownership",
    "summary": "A merchant's products and users also belong to their zone company",
    "version": "19.0.1.1.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Multi Company",
    "license": "AGPL-3",
    "depends": [
        "res_company_zone",
        "product_multi_company",
        # For the ownership guard hook: a zone company must not count as the
        # merchant's own shop when the guard asks "did you keep one of yours".
        "multi_company_field_visible",
    ],
    "data": [
        "views/res_company_views.xml",
    ],
    "installable": True,
}
