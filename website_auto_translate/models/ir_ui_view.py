# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class IrUiView(models.Model):
    _name = "ir.ui.view"
    _inherit = ["ir.ui.view", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["arch_db"]

    def _auto_translate_touched(self, vals):
        """``arch`` and ``arch_base`` are inverses that land on ``arch_db``.

        The website builder never writes ``arch_db`` directly, so watching only
        the stored field would mean page edits are silently never translated.
        """
        if {"arch", "arch_base", "arch_db"} & set(vals):
            return ["arch_db"]
        return []

    def _auto_translate_scoped(self):
        """Only pages a merchant actually edited, never a core view.

        A view with no ``website_id`` ships with Odoo or with one of our
        addons; its wording belongs to the ``.po`` files and translating it
        here would fight the module every time it is updated. Only the
        copy-on-write pages a merchant edited in the website builder are ours
        to translate.
        """
        enabled = self.env["res.company"]._auto_translate_companies()
        if not enabled:
            return self.browse()
        websites = (
            self.env["website"].sudo().search([("company_id", "in", enabled.ids)])
        )
        if not websites:
            return self.browse()
        return self.sudo().filtered(lambda view: view.website_id in websites)
