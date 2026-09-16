# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Website Sale Marketplace",
    "version": "19.0.1.7.0",
    "category": "Website/eCommerce",
    "summary": "Aggregate the published products of every company on a "
    "marketplace website while merchant sites stay isolated",
    "author": "MikeColangelo",
    "website": "https://github.com/CanariasConectada/canarias-platform",
    "license": "AGPL-3",
    "maintainers": ["mikecolangelo"],
    "development_status": "Beta",
    "depends": [
        "website_sale",
        "product_multi_company",
        # The in_store delivery method every merchant shop is given
        # (res.company._ensure_shop_pickup_carrier).
        "website_sale_collect",
    ],
    "data": [
        "views/website_views.xml",
    ],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "auto_install": False,
}
