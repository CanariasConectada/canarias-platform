# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).


def post_init_hook(env):
    """Backfill existing products for any website that is already a marketplace
    at install time (add its company to every product's allowed companies)."""
    env["website"].sudo().search(
        [("is_marketplace", "=", True)]
    )._sync_marketplace_products()
