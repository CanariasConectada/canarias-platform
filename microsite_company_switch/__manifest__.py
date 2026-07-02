{
    "name": "Microsite Company Switch",
    "version": "19.0.1.5.0",
    "category": "Website",
    "summary": "Sincroniza cookie de compañía y gestiona aislamiento de contactos",
    "description": """
        Este módulo:
        1. Sincroniza la cookie 'cids' con el company_id del usuario
        2. Permite el cambio de compañía desde el switcher de Odoo
        3. Gestiona aislamiento de contactos por compañía
    """,
    "depends": ["base", "web", "website"],
    "data": [
        # Reglas V3: Aislamiento estricto por compañía seleccionada
        # Fase 3 - 2026-03-25: Solo compañía seleccionada, NO My Company por defecto
        "security/security_rules_v3.xml",
        # JavaScript para company switcher en frontend
        "views/assets.xml",
        # Patch para evitar redirección al cambiar de website
        "views/assets_switcher_patch.xml",
    ],
    "installable": True,
    "application": False,
    'author': 'MikeColangelo',
    "license": "LGPL-3",
    'website': 'https://github.com/CanariasConectada/canarias-platform',
}