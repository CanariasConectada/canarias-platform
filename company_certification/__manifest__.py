# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Company Certification",
    "version": "19.0.1.0.0",
    "category": "Marketing/Surveys",
    "summary": "Parameterizable company certification seals built on Survey",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "survey",
        "website",
        "mail",
    ],
    "data": [
        "security/company_certification_security.xml",
        "security/ir.model.access.csv",
        "views/certification_type_views.xml",
        "views/res_company_views.xml",
        "views/survey_survey_views.xml",
        "views/survey_user_input_views.xml",
        "views/website_templates.xml",
        "data/survey_silver_economy.xml",
        "data/survey_sustainability.xml",
        "data/certification_type_data.xml",
        "data/mail_template_data.xml",
        "data/ir_cron_data.xml",
    ],
    "demo": [
        "demo/company_certification_demo.xml",
    ],
    "installable": True,
    "application": True,
}
