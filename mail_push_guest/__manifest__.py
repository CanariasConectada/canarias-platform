# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Mail Push Guest",
    "version": "19.0.1.3.0",
    "category": "Discuss",
    "summary": "Web Push notifications for anonymous mail.guest personas",
    "author": "Canarias Conectada",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "mail",
    ],
    "assets": {
        # The foreground chime (throttle, mute, "not my own message"), shared
        # by the backend web client and the website pages that import it.
        "web.assets_backend": [
            "mail_push_guest/static/src/js/chime.js",
        ],
        "web.assets_frontend": [
            "mail_push_guest/static/src/js/chime.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
