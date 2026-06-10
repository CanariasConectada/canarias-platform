{
    'name': 'Partner Microsite Manager',
    'version': '1.3.9',
    'category': 'Website',
    'summary': 'Gestión de microsites desde el contacto de la compañía',
    'description': """
        Añade una pestaña "Microsite" en el formulario de contactos (res.partner)
        para gestionar el contenido del website asociado a la compañía.
        Sincroniza bidireccionalmente partner ↔ website.
    """,
    'author': 'MikeColangelo',
    'depends': ['base', 'website', 'theme_corporate_multi'],
    'data': [
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
}