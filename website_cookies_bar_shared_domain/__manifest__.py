# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

{
    "name": "Website Cookies Bar Shared Domain",
    "summary": "Share the cookies bar consent across the subdomains of one "
    "registrable domain",
    "version": "19.0.1.0.0",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "category": "Website",
    "license": "AGPL-3",
    "depends": ["website"],
    "data": [
        "data/ir_config_parameter.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_cookies_bar_shared_domain/static/src/js/shared_consent_cookie.js",
            "website_cookies_bar_shared_domain/static/src/js/consent_cookie_patches.js",
        ],
    },
    "installable": True,
}
