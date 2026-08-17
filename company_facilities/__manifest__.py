# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Company Facilities",
    "version": "19.0.2.0.0",
    "category": "Website",
    "summary": "Facilities and services a shop offers, by subdivision and icon",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    # ``website_auto_translate`` rather than plain ``website``: what a shop
    # ticks here is rendered to visitors in four languages, and a catalogue
    # somebody extends from the interface has to reach the queue on its own.
    # A shop adding "Parking gratuito" must not need a developer for the
    # German to appear.
    "depends": [
        "partner_microsite_manager",
        "website_auto_translate",
    ],
    "data": [
        "security/company_facilities_security.xml",
        "security/ir.model.access.csv",
        "views/company_facility_category_views.xml",
        "views/company_facility_views.xml",
        "views/res_company_views.xml",
        "views/website_templates.xml",
        "views/menus.xml",
        "data/company_facility_data.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "company_facilities/static/src/scss/facilities.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
