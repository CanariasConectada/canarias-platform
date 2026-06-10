{
    'name': 'Microsite Menu Manager',
    'version': '1.0.0',
    'category': 'Website',
    'summary': 'Gestor centralizado de menús para microsites multi-website',
    'description': """
    Centraliza la creación y sincronización de menús de website según el tipo de site:
    - Canarias Conectada (padre)
    - Zonas Comerciales (Guanarteme, Tamaraceite, Lomo Los Frailes)
    - Microsites individuales

    Incluye lógica condicional para el menú de Reseñas según enable_reviews.
    """,
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
    'depends': [
        'website',
        'website_directory',
        'partner_reviews',
        'microsite_zones',
        'event',
    ],
    'data': [],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
    'post_init_hook': 'post_init_hook',
}
