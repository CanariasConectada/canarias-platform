# -*- coding: utf-8 -*-
{
    "name": "Website Login Branding",
    "version": "19.0.2.1.0",
    "category": "Website",
    "summary": "Branded login card + anonymous portal guest access with Discuss & push",
    "description": """
Website Login Branding
======================
Turns the plain website auth page into a single, on-brand card: the Canarias
Conectada logo on top, the ZCA (Zonas Comerciales Abiertas) subvention logo at
the foot, and the login/signup/reset form in between with a clear primary
action.

It also replaces the old anonymous "continue as guest" link with a real,
lightweight identity: the "Entrar como invitado" button now logs the visitor
in as an anonymous PORTAL user (via the /guest/enter controller) so they get a
Discuss inbox and can receive web-push notifications. Repeat clicks are made
idempotent by a signed reuse cookie, brand-new sessions are soft-capped against
abuse, and idle empty guests are purged by a daily cron.
    """,
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "depends": [
        "website",
        "mail",
        "portal",
    ],
    "data": [
        "data/ir_cron.xml",
        "views/login_templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_login_branding/static/src/scss/login.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
