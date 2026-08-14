# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class EventEvent(models.Model):
    _name = "event.event"
    _inherit = ["event.event", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["name", "subtitle", "description"]

    def _auto_translate_scoped(self):
        enabled = self.env["res.company"]._auto_translate_companies()
        if not enabled:
            return self.browse()
        return self.sudo().filtered(
            lambda event: not event.company_id or event.company_id in enabled
        )
