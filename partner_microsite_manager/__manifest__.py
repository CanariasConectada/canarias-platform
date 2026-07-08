# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Partner Microsite Manager",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "Merchant microsite content managed from the company form",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website",
    ],
    "data": [
        "views/microsite_templates.xml",
        "views/res_company_views.xml",
        "views/res_partner_views.xml",
    ],
    "demo": [
        "demo/microsite_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
