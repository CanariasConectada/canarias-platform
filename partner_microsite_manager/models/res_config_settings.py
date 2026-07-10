# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    # Editable mirror of ``website.is_microsite_themed`` so the corporate
    # microsite look can be toggled from Website > Configuration > Settings
    # (per selected website), instead of only from a shell session.
    is_microsite_themed = fields.Boolean(
        related="website_id.is_microsite_themed",
        readonly=False,
        string="Corporate Microsite Look",
        help="Render the corporate microsite footer (black footer with "
        "social links, legal pages and certification badges) on the "
        "selected website. Leave off for the directory and the main website.",
    )
