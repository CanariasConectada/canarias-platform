# -*- coding: utf-8 -*-
{
    'name': 'Partner Reviews - Reseñas de Comercios',
    'version': '19.0.1.0.1',
    'category': 'Website',
    'summary': 'Sistema de reseñas con valoraciones y comentarios para microsites de comercios',
    'description': """
Partner Reviews
===============
Módulo para gestionar reseñas de clientes en los microsites de comercios:
* Valoraciones con estrellas (1-5)
* Comentarios textuales con moderación automática
* Palabras prohibidas y filtro de contenido
* Página de reseñas por microsite
* Integración con directorio de comercios
    """,
    'author': 'MikeColangelo',
    'website': 'https://github.com/CanariasConectada/canarias-platform',
    'depends': ['base', 'website', 'partner_microsite_manager', 'mail'],
    'data': [
        'security/partner_reviews_security.xml',
        'security/ir.model.access.csv',
        'security/partner_reviews_rules.xml',
        'data/email_template_moderacion.xml',
        'data/palabras_prohibidas_default.xml',
        'views/partner_review_settings_views.xml',
        'views/partner_review_rating_views.xml',
        'views/partner_review_comment_views.xml',
        'views/partner_review_palabra_prohibida_views.xml',
        'views/partner_review_templates.xml',
        'views/res_partner_views.xml',
        'views/partner_review_menus.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'partner_reviews/static/src/scss/partner_reviews.scss',
            'partner_reviews/static/src/js/partner_reviews.js',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
