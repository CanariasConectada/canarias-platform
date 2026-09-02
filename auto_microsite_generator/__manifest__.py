# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Auto Microsite Generator",
    "version": "19.0.2.1.0",
    "category": "Website",
    "summary": "Provision a website, homepage and menu when a company is created",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_config_parameter.xml",
        "views/microsite_templates.xml",
        # Before the company form: that form's button resolves the wizard
        # action by xmlid, and an xmlid that does not exist yet is a
        # ParseError at install time, not a missing button.
        "wizards/microsite_creation_views.xml",
        "views/res_company_views.xml",
    ],
    "demo": [
        "demo/auto_microsite_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "uninstall_hook": "uninstall_hook",
}
