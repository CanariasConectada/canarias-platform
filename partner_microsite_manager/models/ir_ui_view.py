# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

from .res_company import LEGACY_HOMEPAGE_KEY_RE, LIVE_RELINK_CONTEXT_KEY

ARCH_FIELDS = frozenset({"arch", "arch_db", "arch_base"})


class IrUiView(models.Model):
    _inherit = "ir.ui.view"

    def write(self, vals):
        """Relink a legacy homepage again after the website builder saved it.

        Saving a page in the builder writes the RENDERED html of the page
        back into its arch (``html_editor``'s ``ir.ui.view.save`` ->
        ``replace_arch_section`` -> ``write({"arch": ...})``): every t-call
        of a live value becomes the literal value of that day, and the page
        stops following the company again. The live blocks carry a
        ``data-cc-live`` marker that survives the round trip, so running the
        relinker on the saved view puts the t-calls back.
        """
        result = super().write(vals)
        if self.env.context.get(
            LIVE_RELINK_CONTEXT_KEY
        ) or not ARCH_FIELDS.intersection(vals):
            return result
        legacy = self.filtered(
            lambda view: view.key and LEGACY_HOMEPAGE_KEY_RE.match(view.key)
        )
        if legacy:
            self.env["res.company"].sudo()._relink_legacy_homepage_live_data(
                views=legacy
            )
        return result
