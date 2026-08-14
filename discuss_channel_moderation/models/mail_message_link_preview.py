# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class MailMessageLinkPreview(models.Model):
    """The wall behind the route guard: a preview cannot be LINKED to a message.

    ``mail.link.preview`` holds the fetched Open Graph payload;
    ``mail.message.link.preview`` is the row that makes it VISIBLE under a
    message, and it is what ``_to_store_defaults`` serves to readers
    (``mail/models/mail_message.py:1098``). Refusing the link here is the same
    move as ``ir.attachment.create``: the route is one door, ``create`` is the
    wall. Today ``_create_from_message_and_notify`` is the only core caller, but
    a future route, widget or module that builds the link some other way is
    covered by this and needs no new review.

    Offending values are DROPPED, not raised on. The only caller iterates the
    returned recordset and reconciles it against the message's existing
    previews (``mail/models/mail_link_preview.py:89-99``), so a short result is
    a shape it already handles; raising would turn a refused preview into a
    failed request for a message that was published perfectly well.
    """

    _inherit = "mail.message.link.preview"

    @api.model_create_multi
    def create(self, vals_list):
        return super().create(
            [vals for vals in vals_list if not self._moderation_is_blocked(vals)]
        )

    @api.model
    def _moderation_is_blocked(self, vals):
        """Whether these values would put a preview under a moderated message."""
        message_id = vals.get("message_id")
        if not message_id:
            return False
        # sudo: the persona asking for the preview has no rights on the message
        # index or on the moderation configuration, and must not be granted any.
        message = self.env["mail.message"].sudo().browse(int(message_id)).exists()
        return bool(message) and message._moderation_previews_blocked()
