{
    'name': 'Zonas para Empresas',
    'version': '19.0.1.7.0',
    'category': 'Technical',
    'summary': 'Gestión de zonas para organizar empresas geográficamente.',
    'description': """
        Módulo para gestionar zonas y asignarlas a empresas.
        
        Características:
        - CRUD completo de zonas
        - Edición directa en lista
        - Filtros y agrupaciones por zona
        - Menú accesible desde Usuarios y Compañías
    """,
    'depends': ['base', 'sale_stock'],
    'data': [
        'security/groups.xml',
        'security/ir.model.access.csv',
        'data/fix_res_partner_rule.xml',
        'views/zone_views.xml',
        'views/res_company_views.xml',
    ],
    'post_init_hook': 'hooks.post_init_hook',
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
}