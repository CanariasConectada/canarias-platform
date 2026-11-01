# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @api.model
    def get_frontend_session_info(self):
        """Tell the page which guest it is, for the chime's own-message guard.

        `push_chime.js` skips a push whose author is the visitor. A logged-in
        visitor is known client side (`user.partnerId`); a guest is not, so
        its own id -- proven by the signed `dgid` cookie, never a parameter --
        is added here. Only the visitor's OWN id reaches their own page.
        """
        info = super().get_frontend_session_info()
        # sudo: mail.push.device is a system model; `_current_guest` only
        # reads the request's own cookie.
        guest = self.env["mail.push.device"].sudo()._current_guest()
        info["cc_guest_id"] = guest.id or False
        return info
