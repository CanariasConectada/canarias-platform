# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Silver Economy Certification",
    "version": "19.0.2.0.0",
    "category": "Marketing/Surveys",
    "summary": "Silver Economy evaluation and certification for companies",
    "author": "Canarias Conectada",
    "maintainers": ["MikeColangelo"],
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "development_status": "Beta",
    "depends": [
        "survey",
        "website",
        "website_directory",
    ],
    "data": [
        "security/silver_economy_security.xml",
        "security/ir.model.access.csv",
        "views/silver_economy_views.xml",
        "views/res_company_views.xml",
        "views/survey_user_input_views.xml",
        "views/silver_economy_website.xml",
        "data/silver_economy_survey.xml",
        "data/silver_economy_filters.xml",
        "data/silver_economy_mail_templates.xml",
        "data/silver_economy_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "silver_economy/static/src/js/silver_start_form.js",
        ],
        "web.assets_frontend": [
            "silver_economy/static/src/scss/silver_economy_public.scss",
        ],
    },
    "installable": True,
    "application": True,
}
