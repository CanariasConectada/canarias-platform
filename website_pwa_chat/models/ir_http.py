# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """Tell the backend Discuss whether to offer "Request support".

        A session flag rather than an RPC from the sidebar: the entry is
        rendered on every Discuss load, and the answer only changes when an
        administrator ticks the support group on this user, after which a
        reload is expected anyway. The route re-checks on click, so a stale
        flag can show a button, never open a conversation for an agent.
        """
        result = super().session_info()
        user = self.env.user
        if user._is_internal():
            Channel = self.env["discuss.channel"]
            result["website_pwa_chat_can_request_support"] = (
                Channel._support_can_request_from_discuss()
            )
            # Walk-in community guests are asked their name before the
            # conversation opens; their account name says nothing.
            result["website_pwa_chat_support_asks_name"] = (
                Channel._support_is_community_guest()
            )
        return result
