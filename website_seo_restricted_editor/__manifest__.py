# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website SEO for Restricted Editors",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "Restricted editors optimise the SEO of their own site's pages",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": ["website"],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
