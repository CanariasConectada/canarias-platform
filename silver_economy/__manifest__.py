# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Silver Economy Certification",
    "version": "19.0.1.4.4",
    "category": "Marketing/Surveys",
    "summary": "Sistema de evaluación y certificación Silver Economy para empresas",
    "description": """
        Módulo de evaluación Silver Economy basado en Survey.
        Permite a usuarios internos evaluar sus empresas mediante un cuestionario
        de 40 preguntas y obtener sellos Bronce, Plata u Oro.

        Características:
        - Cuestionario editable por administradores
        - Control de plazos (3 meses reintento, 1 año renovación)
        - Sellos automáticos por puntuación
        - Auditoría de ediciones admin
        - Notificaciones por email
        - Integración web (microsite y directorio)
    """,
    "author": "MikeColangelo",
    "depends": [
        "survey",
        "contacts",
        "website",
        "website_directory",
        "mail",
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
            "silver_economy/static/src/scss/silver_economy.scss",
            "silver_economy/static/src/js/silver_start_form.js",
        ],
        "web.assets_frontend": [
            "silver_economy/static/src/scss/silver_economy_public.scss",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "AGPL-3",
    "website": "https://github.com/CanariasConectada/canarias-platform",
}
