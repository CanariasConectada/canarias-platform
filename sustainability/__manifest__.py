# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Sustainability Certification",
    "version": "19.0.2.0.0",
    "category": "Marketing/Surveys",
    "summary": "Sustainability evaluation and certification for companies",
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
        "security/sustainability_security.xml",
        "security/ir.model.access.csv",
        "views/sustainability_views.xml",
        "views/res_company_views.xml",
        "views/survey_user_input_views.xml",
        "views/sustainability_website.xml",
        "data/sustainability_survey.xml",
        "data/sustainability_filters.xml",
        "data/sustainability_mail_templates.xml",
        "data/sustainability_cron.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "sustainability/static/src/js/sustainability_start_form.js",
        ],
        "web.assets_frontend": [
            "sustainability/static/src/scss/sustainability_public.scss",
        ],
    },
    "installable": True,
    "application": True,
}
