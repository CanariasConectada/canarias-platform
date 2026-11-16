# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

from .website import PARAM_ENABLED


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Platform-wide, on purpose: the comparator crosses websites (its whole
    # point is "the same product elsewhere"), so a per-website flag would
    # only half switch it off. Stored in ``ir.config_parameter`` and read
    # by ``website._wscc_comparison_enabled()``.
    wscc_comparison_enabled = fields.Boolean(
        string="Price Comparator",
        config_parameter=PARAM_ENABLED,
        help="Show the price comparator on every shop: the Compare buttons on "
        "the product cards, the Compare prices button and its picker on the "
        "product page, and the comparison bar. When disabled the comparator is "
        "not rendered anywhere and its data endpoint answers empty; nothing is "
        "uninstalled, so it can be switched back on at any time.",
    )
