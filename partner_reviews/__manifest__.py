# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Merchant Reviews",
    "version": "19.0.3.0.0",
    "category": "Website",
    "summary": "Customer reviews for merchant websites, built on rating.rating",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Production/Stable",
    # ``partner_microsite_manager`` for the merchant's content editor, where
    # a shop switches its own reviews page on and off (client request
    # 2026-09-16). It does not depend on this module, so there is no cycle.
    # ``website_moderation_forbidden_word`` holds the shared forbidden-word
    # list (one list for reviews and local content comments, 2026-09-22).
    "depends": [
        "partner_microsite_manager",
        "portal_rating",
        "website",
        "website_moderation_forbidden_word",
    ],
    "data": [
        "security/partner_reviews_security.xml",
        "security/ir.model.access.csv",
        "security/partner_reviews_rules.xml",
        "data/mail_template_moderation.xml",
        "views/rating_rating_views.xml",
        "views/res_company_views.xml",
        "views/microsite_content_editor_views.xml",
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
