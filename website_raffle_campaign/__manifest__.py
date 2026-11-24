# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Raffle Campaign",
    "summary": "Receipt-raffle campaigns on a website: banner, public entry "
    "form, legal terms and an audited draw",
    "version": "19.0.1.0.0",
    "category": "Website",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Beta",
    # ``res_company_zone`` is deliberately NOT a dependency: when it is
    # installed the "add all merchants of a zone" helper and the trade name
    # light up, otherwise the campaign works with hand-picked merchants.
    "depends": ["website", "mail", "website_auto_translate"],
    "data": [
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "views/raffle_entry_views.xml",
        "views/raffle_campaign_views.xml",
        "wizard/raffle_entry_reject_wizard_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
