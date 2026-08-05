# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ResCompany(models.Model):
    """Moving a business between neighbourhoods moves its people with it.

    The inherit lives HERE and not in ``res_company_zone`` on purpose. That
    module owns the field and knows nothing about chat: it is installable on a
    database with no Discuss channels at all, and adding a channel side effect
    to its ``write`` would make the zone field impossible to use without this
    module. The dependency points the right way -- chat knows about zones,
    zones do not know about chat.
    """

    _inherit = "res.company"

    def write(self, vals):
        """Re-seat every user of the company when its zone changes.

        The zone of a merchant is READ from their company
        (``res.users._get_chat_zone``), so the company is where the change
        happens and the users are where it has to land. Resolved with one
        ``sudo().search()`` on ``res.users``: the caller editing the company
        form has no reason to hold rights over other people's accounts.
        """
        result = super().write(vals)
        if "commercial_zone" in vals:
            users = (
                self.env["res.users"].sudo().search([("company_id", "in", self.ids)])
            )
            users._sync_zone_channels()
        return result
