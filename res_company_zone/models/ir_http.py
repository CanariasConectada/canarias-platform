# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """The company switcher builds its own labels, bypassing display_name.

        ``web`` fills ``allowed_companies`` from ``comp.name``, so the one
        list the operators actually scan with 282 shops in it kept showing
        the legal name after the company started answering to its trade name
        everywhere else. The label is taken from ``display_name`` rather than
        formatted again here: one definition of how a shop is written.
        """
        info = super().session_info()
        user_companies = info.get("user_companies") or {}
        for key in ("allowed_companies", "disallowed_ancestor_companies"):
            entries = user_companies.get(key) or {}
            if not entries:
                continue
            # sudo for the same reason the base method does it: the switcher
            # lists ancestor companies the user may not read.
            for company in self.env["res.company"].sudo().browse(list(entries)):
                entries[company.id]["name"] = company.display_name
        return info
