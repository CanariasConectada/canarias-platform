# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class RaffleEntryRejectWizard(models.TransientModel):
    _name = "raffle.entry.reject.wizard"
    _description = "Reject raffle entries"

    entry_ids = fields.Many2many("raffle.entry", string="Entries")
    reason = fields.Char(required=True)

    def action_confirm(self):
        self.ensure_one()
        self.entry_ids.write({"state": "rejected", "reject_reason": self.reason})
        return {"type": "ir.actions.act_window_close"}
