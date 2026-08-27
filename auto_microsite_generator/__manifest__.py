# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Auto Microsite Generator",
    "version": "19.0.1.5.0",
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
        "data/ir_config_parameter.xml",
        "views/microsite_templates.xml",
    ],
    "demo": [
        "demo/auto_microsite_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
    "uninstall_hook": "uninstall_hook",
}
