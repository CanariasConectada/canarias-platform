# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Partner Microsite Manager",
    "version": "19.0.2.3.2",
    "category": "Website",
    "summary": "Merchant microsite content managed from the company form",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website",
        "website_map_embed",
        "spreadsheet_dashboard",
    ],
    "data": [
        "security/ir.model.access.csv",
        "security/ir_rule.xml",
        "views/microsite_templates.xml",
        "views/microsite_layout.xml",
        "views/microsite_header_contact.xml",
        "views/core_menu_gating.xml",
        "views/microsite_legal.xml",
        "views/res_company_views.xml",
        "views/microsite_content_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_partner_views.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "partner_microsite_manager/static/src/scss/microsite_footer.scss",
            "partner_microsite_manager/static/src/scss/microsite_corrections.scss",
            "partner_microsite_manager/static/src/scss/microsite_banner.scss",
            "partner_microsite_manager/static/src/scss/microsite_opening_hours.scss",
            "partner_microsite_manager/static/src/js/microsite_opening_hours.js",
        ],
    },
    "demo": [
        "demo/microsite_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
