{
    'name': 'ZCA Platform',
    'version': '19.0.1.3.0',
    'post_init_hook': 'post_init',
    'category': 'Website',
    'summary': 'Plataforma de Zonas Comerciales Abiertas',
    'description': '''
        Módulo para gestionar múltiples comercios como empresas independientes.
        Incluye directorio público, microsites por comercio, filtros avanzados y AJAX.
    ''',
    'author': 'MikeColangelo',
    'depends': ['website', 'website_sale', 'sale', 'stock', 'account', 'purchase', 'crm', 'project', 'hr'],
    'data': [
        'data/zca_groups.xml',
        'security/ir_model_access.xml',
        'security/ir_rule.xml',
        'views/zca_comercio_views.xml',
        'views/zca_menu.xml',
        'templates/directorio.xml',
        'templates/microsite.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'zca_platform/static/src/css/zca_styles.css',
            'zca_platform/static/src/js/zca_directorio.js',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
}