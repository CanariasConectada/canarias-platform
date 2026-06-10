# -*- coding: utf-8 -*-
{
    'name': 'Memoria Viva',
    'version': '19.0.2.2.0',
    'category': 'Website',
    'summary': 'Galería de historias e imágenes por microsite',
    'description': """
Memoria Viva
============
Módulo para gestionar y publicar historias/memorias de una zona comercial:
* Backend CRUD restringido a administradores y aprobadores
* Website con galería, mapa y formulario público
* API JSON para envío anónimo
* Sistema de anuncios/ofertas con gestión backend
* Importación/exportación masiva
    """,
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
    'depends': ['base', 'website'],
    'data': [
        'data/website_menu.xml',
        'security/memoria_viva_security.xml',
        'security/ir.model.access.csv',
        'security/memoria_viva_rules.xml',
        'views/memoria_viva_categorias_views.xml',
        'views/memoria_viva_tags_views.xml',
        'views/memoria_viva_evento_views.xml',
        'views/memoria_viva_anuncio_views.xml',
        'views/memoria_viva_historia_views.xml',
        'views/memoria_viva_settings_views.xml',
        'views/memoria_viva_comentario_views.xml',
        'views/memoria_viva_palabra_prohibida_views.xml',
        'views/memoria_viva_templates.xml',
        'views/memoria_viva_menus.xml',
        'data/memoria_viva_demo.xml',
        'data/categorias_nuevas.xml',
        'data/seccion_editable.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'memoria_viva/static/src/css/memoria_viva.scss',
            # Los JS se cargan inline en el template para evitar dependencias
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
