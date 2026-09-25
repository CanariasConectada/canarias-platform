# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class IrHttp(models.AbstractModel):
    """Tell the web client whether the session belongs to a community guest.

    The guest profile of Discuss (no calls, no member list, no header
    actions, the community channel opened on arrival) is applied by OWL
    patches in the backend bundle, and those patches need ONE trustworthy
    flag to pivot on. The server decides it here; the client never infers it.
    Hiding buttons is presentation only: what a guest may actually read and
    join is enforced by the record rules in ``security/``.
    """

    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        user = self.env.user
        is_guest = bool(user.is_community_guest)
        info["is_community_guest"] = is_guest
        if is_guest:
            channel = self.env["res.users"]._community_default_channel()
            info["community_default_channel_id"] = channel.id or False
        return info
