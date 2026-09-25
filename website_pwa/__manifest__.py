# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website PWA",
    "version": "19.0.3.0.1",
    "category": "Website",
    "summary": "Installable app for the public website, one per microsite",
    "description": """
        Turns each public website into an installable Progressive Web App.

        Odoo ships a PWA for the BACKEND only: /web/manifest.webmanifest is
        scoped to /odoo and carries Odoo's own icon, so installing it gives
        the visitor the ERP, not the shop. OCA's web_pwa_customize customises
        that same backend app; OCA/pwa-builder is an empty repository on 16.0,
        18.0 and 19.0. Nothing covered the public side, hence this module.

        What it adds:

        - A manifest per website, built from the website's own name, logo and
          colours, scoped to / so the installed app opens the microsite.
        - A service worker with an offline fallback page.
        - An "install this app" section that can be dropped anywhere from the
          editor, with the Android install prompt and iOS instructions (iOS
          has no programmatic prompt).
        - A per-website switch, so the app can be enabled for one merchant and
          not another.
        - A "Download Canarias Conectada" block that other pages (the login
          page first) can include, driven by the same script as the snippet.
        - A "Canarias Conectada" home entry in the backend systray and user
          menu, so an internal user who opened Discuss inside the installed
          app can get back to the website.
    """,
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website",
    ],
    "data": [
        "views/website_views.xml",
        "views/templates.xml",
        "views/snippets.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_pwa/static/src/js/pwa_install.js",
            "website_pwa/static/src/scss/pwa_install.scss",
        ],
        # Loaded for every internal user: the way back from the backend to the
        # public site is not a website-editor feature, it is navigation.
        "web.assets_backend": [
            "website_pwa/static/src/backend/home_systray.js",
            "website_pwa/static/src/backend/home_systray.xml",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
