# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website PWA Push",
    "version": "19.0.1.0.1",
    "category": "Website",
    "summary": "Web Push notifications for the public website app",
    # Odoo renders this with docutils on every install. Keep it valid RST:
    # the bullet list needs a blank line before it and the whole block must
    # start at column 0, or docutils logs "Unexpected indentation" (ERROR) for
    # each install of the module.
    "description": """
Adds Web Push to the public Progressive Web App built by website_pwa.

website_pwa makes each microsite installable and serves a service worker;
mail_push_guest lets an anonymous visitor own a subscription and pushes
channel messages to guests. Nothing joined the two: the worker had no push
handler and no page ever asked for permission.

What it adds:

- A per-website switch, separate from the app switch, so push can be piloted
  on one website while every other one is untouched.
- push / notificationclick / pushsubscriptionchange handlers, appended to the
  worker website_pwa already serves, and only when the switch is on.
- A frontend snippet with an "Activar avisos" button. Permission is only ever
  requested from that click: an unprompted request is an abuse signal in
  Chrome and a no-op in Safari.
- iOS is told the truth: Safari only grants a subscription inside a PWA
  installed to the home screen, so an uninstalled iPhone gets the install
  instructions instead of a button that cannot work.
""",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website_pwa",
        "mail_push_guest",
    ],
    "data": [
        "views/website_views.xml",
        "views/templates.xml",
        "views/snippets.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_pwa_push/static/src/js/pwa_push.js",
            "website_pwa_push/static/src/scss/pwa_push.scss",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
