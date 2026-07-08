# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Merchant Reviews",
    "version": "19.0.2.0.0",
    "category": "Website",
    "summary": "Customer reviews for merchant websites, built on rating.rating",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Production/Stable",
    "depends": [
        "portal_rating",
        "website",
    ],
    "data": [
        "security/partner_reviews_security.xml",
        "security/ir.model.access.csv",
        "security/partner_reviews_rules.xml",
        "data/forbidden_words.xml",
        "data/mail_template_moderation.xml",
        "views/rating_rating_views.xml",
        "views/review_forbidden_word_views.xml",
        "views/res_company_views.xml",
        "views/res_config_settings_views.xml",
        "views/website_templates.xml",
        "views/partner_reviews_menus.xml",
    ],
    "demo": [
        "demo/partner_reviews_demo.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "partner_reviews/static/src/scss/partner_reviews.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
