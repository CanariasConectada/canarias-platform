# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Canarias Conectada Company Categories",
    "version": "19.0.1.0.0",
    "category": "Contacts",
    "summary": "Seed the Canarias Conectada business taxonomy as company categories",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["MikeColangelo"],
    "development_status": "Production/Stable",
    "depends": [
        "res_company_category",
    ],
    "demo": [
        "demo/company_category_demo.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
