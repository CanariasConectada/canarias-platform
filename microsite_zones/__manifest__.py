{
    'name': 'Microsite Zones',
    'version': '1.0',
    'summary': 'Manage commercial zones and microsites',
    'category': 'Website',
    'depends': ['base', 'website', 'website_sale'],
    'data': [
        'security/ir.model.access.csv',
        'views/website_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
}