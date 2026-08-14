# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "Website Login Loader",
    "version": "19.0.2.0.0",
    "category": "Website",
    "summary": "Visible progress while the auth page and the next one load",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website",
    ],
    "data": [
        "views/login_loader_templates.xml",
    ],
    # No "assets" key, and that is the whole design. Everything this module
    # ships is inlined into the auth page: a bundled file would arrive in the
    # same render-blocking payload whose wait it is supposed to cover, which
    # is a loader that appears once the loading is over.
    "installable": True,
    "application": False,
    "auto_install": False,
    "license": "LGPL-3",
}
