# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Sostenibilidad Certification",
    "version": "19.0.1.5.0",
    "category": "Marketing/Surveys",
    "summary": "Sistema de evaluación y certificación Sostenibilidad para empresas",
    "description": """
        Módulo de evaluación Sostenibilidad basado en Survey.
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
        # The questionnaire lives here now; this module only flags it.
        "company_certification",
        "contacts",
        "website",
        "website_directory",
        "mail",
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
            "sustainability/static/src/scss/sustainability.scss",
            "sustainability/static/src/js/sustainability_start_form.js",
        ],
        "web.assets_frontend": [
            "sustainability/static/src/scss/sustainability_public.scss",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "license": "AGPL-3",
    "website": "https://github.com/CanariasConectada/canarias-platform",
}
