# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Directory - Company Certification",
    "version": "19.0.1.2.0",
    "category": "Website",
    "summary": "Certification badges and filters in the business directory",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "company_certification",
        "website_directory",
    ],
    "data": [
        "views/website_directory_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_directory_company_certification/static/src/css/directory_certification.css",
        ],
    },
    "installable": True,
    "auto_install": True,
}
