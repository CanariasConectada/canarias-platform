# -*- coding: utf-8 -*-
{
    'name': 'Lugares de Interés',
    'version': '19.0.2.2.0',
    'category': 'Website',
    'summary': 'Galería de historias e imágenes por microsite',
    'description': """
Lugares de Interés
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
        'security/lugares_interes_security.xml',
        'security/ir.model.access.csv',
        'security/lugares_interes_rules.xml',
        'views/lugares_interes_categorias_views.xml',
        'views/lugares_interes_tags_views.xml',
        'views/lugares_interes_evento_views.xml',
        'views/lugares_interes_anuncio_views.xml',
        'views/lugares_interes_historia_views.xml',
        'views/lugares_interes_palabra_prohibida_views.xml',
        'views/lugares_interes_settings_views.xml',
        'views/lugares_interes_comentario_views.xml',
        'views/lugares_interes_templates.xml',
        'views/lugares_interes_menus.xml',
        'data/lugares_interes_demo.xml',
        'data/categorias_nuevas.xml',
        'data/seccion_editable.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'lugares_interes/static/src/css/lugares_interes.scss',
            # Los JS se cargan inline en el template para evitar dependencias
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
