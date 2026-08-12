# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Sale Comparison — Canarias",
    "version": "19.0.1.0.0",
    "category": "Website",
    "summary": "A modern, always-available product comparison on the Canarias shop",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        # The comparison engine we build on: the compare list, the drawer and
        # the comparison table are all core to this module. We only change how
        # it looks and WHICH products may enter it.
        "website_sale_comparison",
        # The Canarias shop whose cards we add the button to.
        "website_sale_canarias",
    ],
    "data": [
        "views/templates.xml",
    ],
    "assets": {
        "web.assets_frontend": [
            "website_sale_comparison_canarias/static/src/css/comparison_canarias.css",
            "website_sale_comparison_canarias/static/src/js/comparison_canarias.js",
        ],
    },
    "installable": True,
    "application": False,
    "auto_install": False,
}
