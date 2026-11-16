# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.tools import format_datetime


class DiscussChannelPendingMessage(models.Model):
    """Give the author's UI the body of their own held message.

    The engine's bus payload is deliberately minimal (id, channel, state,
    author name, rejection reason, published message id): enough for a client
    that only needs to KNOW about the state change. The Discuss placeholder
    this module ships also has to SHOW the held text inline, so the payload
    grows the body and a display date.

    No leak is opened by that: the same payload object reaches exactly two
    audiences, the AUTHOR (`_notify_author`, their own words back at them)
    and the channel's MODERATORS (`_notify_moderators`, who read the full
    row in the queue anyway).
    """

    _inherit = "discuss.channel.pending.message"

    def _moderation_bus_payload(self):
        payload = super()._moderation_bus_payload()
        payload.update(self._community_pending_client_data())
        return payload

    def _community_pending_client_data(self):
        """The one client-facing shape of a held row, used by BOTH transports.

        The bus notification (live update) and the channel's store attr
        (reload survival) must describe a row identically, or the placeholder
        would change shape the moment the page is refreshed. Keeping the dict
        in one method is what enforces that.

        ``body`` is the row's Html field, sanitised on write by the field
        itself (``sanitize=True``); the client renders it as markup on the
        strength of that server-side sanitisation, same trust chain as a
        published message body.
        """
        self.ensure_one()
        row = self.sudo()
        return {
            "id": row.id,
            "state": row.state,
            "body": str(row.body or ""),
            "date": (
                format_datetime(self.env, row.create_date) if row.create_date else ""
            ),
            "rejection_reason": row.rejection_reason or "",
        }
