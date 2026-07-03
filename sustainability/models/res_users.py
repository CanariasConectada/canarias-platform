# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models


class ResUsers(models.Model):
    _inherit = "res.users"

    def action_open_sustainability_evaluations(self):
        """Open the list of Sustainability evaluations of the user's companies."""
        self.ensure_one()
        return {
            "name": _("My Sustainability evaluations"),
            "type": "ir.actions.act_window",
            "res_model": "survey.user_input",
            "view_mode": "list,form",
            "domain": [
                ("survey_id.is_sustainability", "=", True),
                ("company_id", "in", self.company_ids.ids),
                ("test_entry", "=", False),
            ],
            "context": {"create": False},
        }
