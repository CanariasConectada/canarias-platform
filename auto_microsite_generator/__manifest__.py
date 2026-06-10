{
    'name': 'Auto Microsite Generator',
    'version': '1.0.0',
    'category': 'Website',
    'summary': 'Generación automática de microsites y validación batch',
    'description': """
        Módulo independiente que intercepta la creación de compañías (res.company)
        para generar automáticamente un microsite completo (website, homepage,
        menús, theme views y campos por defecto).

        Incluye herramientas de validación batch para auditar la calidad de
        microsites existentes: campos vacíos, secciones HTML incompletas,
        detección de Lorem ipsum y reportes ejecutables manualmente o vía cron.
    """,
    'author': 'MikeColangelo',
    'depends': ['partner_microsite_manager', 'website', 'theme_corporate_multi'],
    'data': [
        'security/ir.model.access.csv',
        'data/cron.xml',
        'data/server_actions.xml',
        'views/validation_report_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
    'auto_install': False,
    'website': 'https://github.com/CanariasConectada/canarias-platform',
}