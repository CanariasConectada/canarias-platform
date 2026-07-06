# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    """Replaces the legacy ``partner.review.settings`` singleton with the
    standard settings + system parameter pattern."""

    _inherit = "res.config.settings"

    partner_reviews_allow_comments = fields.Boolean(
        string="Allow Review Comments",
        config_parameter="partner_reviews.allow_comments",
        default=True,
        help="When disabled, customers can still rate with stars but the "
        "comment box is hidden on every reviews page.",
    )
