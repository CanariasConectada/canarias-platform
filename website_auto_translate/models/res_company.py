# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    auto_translate_enabled = fields.Boolean(
        string="Translate this shop automatically",
        default=False,
        help="Content owned by this company is queued for automatic "
        "translation whenever it is saved. Off by default so the rollout can "
        "start with the portal and the commercial zones rather than every shop "
        "at once.",
    )

    def _auto_translate_companies(self):
        """Companies opted into the rollout, as a cached-friendly search."""
        return (
            self.env["res.company"]
            .sudo()
            .search([("auto_translate_enabled", "=", True)])
        )
