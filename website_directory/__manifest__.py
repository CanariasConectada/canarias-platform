# -*- coding: utf-8 -*-
{
    'name': 'Website Directory - Canarias Conectada',
    'version': '19.0.4.6.0',
    'category': 'Website',
    'summary': 'Directorio de empresas con filtros por zona y categoría',
    'description': """
Directorio de Empresas - Canarias Conectada
============================================

Módulo que permite mostrar un directorio de empresas/microsites con:
* Cards visuales con imagen/logo de la empresa
* Filtros por zona y categoría
* Redirección a microsites externos
* Multi-website compatible

Rutas disponibles:
* /directorio - Lista completa de empresas
* /directorio/zona/<zona> - Filtrado por zona
* /directorio/categoria/<categoria> - Filtrado por categoría
    """,
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
    'depends': ['website', 'business_category_hierarchy'],
    'data': [
        'security/ir.model.access.csv',
        'views/website_directory_templates.xml',
        'views/res_company_views.xml',
        'data/website_directory_data.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            # Assets moved to template inline for compatibility
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
