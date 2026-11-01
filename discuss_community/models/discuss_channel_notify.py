# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.fields import Domain

# The community channels: the platform-wide one and the three neighbourhood
# ones, all seeded by `discuss_channel_zone`. Owner decision of 2026-09-26:
# every PUBLISHED message there notifies every member, not only @mentions.
COMMUNITY_CHANNEL_XMLIDS = (
    "discuss_channel_zone.channel_canarias",
    "discuss_channel_zone.channel_guanarteme",
    "discuss_channel_zone.channel_tamaraceite",
    "discuss_channel_zone.channel_lomolosfrailes",
)

# Message types core notifies at all on a channel
# (mail/models/discuss/discuss_channel.py, `_notify_get_recipients`).
NOTIFIED_MESSAGE_TYPES = ("comment", "email", "email_outgoing", "whatsapp_message")


class DiscussChannel(models.Model):
    _inherit = "discuss.channel"

    def _community_channel_ids(self):
        """Ids of the community channels that are installed."""
        ids = set()
        for xmlid in COMMUNITY_CHANNEL_XMLIDS:
            channel = self.env.ref(xmlid, raise_if_not_found=False)
            if channel:
                ids.add(channel.id)
        return ids

    def _notify_get_recipients(self, message, msg_vals=False, **kwargs):
        """In the community channels an UNSET preference means "all".

        Core resolves a member's unset `custom_notifications` through the
        user's `res.users.settings.channel_notifications`, and when that is
        unset too a `channel` notifies @mentions only. So a resident heard
        nothing about the neighbourhood noticeboard unless named.

        For these four channels only, this adds the members core left out
        BECAUSE both preferences are unset, as `web_push` recipients exactly
        shaped like core's. An explicit choice is left to core: member
        "mentions" or "no_notif", or user-level "no_notif". No member row is
        written, so new members get it too and nobody's choice is overwritten.

        Guests (`mail.guest` members) are pushed by `mail_push_guest`, which
        already treats an unset preference as "all".

        Moderation needs nothing here: a held message never reaches the
        notification step (`discuss_channel_moderation` stores a pending row
        and returns an empty message), and approval publishes through core
        `message_post`, which is when this runs.
        """
        recipients_data = super()._notify_get_recipients(
            message, msg_vals=msg_vals, **kwargs
        )
        if len(self) != 1 or self.channel_type != "channel":
            return recipients_data
        msg_vals = msg_vals or {}
        message_type = (
            msg_vals["message_type"]
            if "message_type" in msg_vals
            else message.message_type
        )
        if message_type not in NOTIFIED_MESSAGE_TYPES:
            return recipients_data
        if self.id not in self._community_channel_ids():
            return recipients_data
        author_id = msg_vals.get("author_id") or message.author_id.id
        known_ids = [recipient["id"] for recipient in recipients_data]
        # Same filters as core (author, archived partner, muted, busy), with
        # "both preferences unset" instead of "mentioned".
        domain = Domain.AND(
            [
                [("channel_id", "=", self.id)],
                [("partner_id", "!=", False)],
                [("partner_id", "!=", author_id or False)],
                [("partner_id", "not in", known_ids)],
                [("partner_id.active", "=", True)],
                [("mute_until_dt", "=", False)],
                [("partner_id.user_ids.manual_im_status", "!=", "busy")],
                [("custom_notifications", "=", False)],
                [
                    (
                        "partner_id.user_ids.res_users_settings_ids"
                        ".channel_notifications",
                        "=",
                        False,
                    )
                ],
            ]
        )
        # sudo: discuss.channel.member - the same read core does to list the
        # members of the channel being notified.
        members = self.env["discuss.channel.member"].sudo().search(domain)
        for member in members:
            recipients_data.append(
                {
                    "active": True,
                    "id": member.partner_id.id,
                    "is_follower": False,
                    "groups": [],
                    "lang": member.partner_id.lang,
                    "notif": "web_push",
                    "share": member.partner_id.partner_share,
                    "type": "customer",
                    "uid": False,
                    "ushare": False,
                }
            )
        return recipients_data
