# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Community channels push every PUBLISHED message to every member.

Owner decision of 2026-09-26. The web push send is mocked; what is asserted
is which endpoints core's sender was asked to reach.
"""

import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.mail.models import mail_thread
from odoo.addons.mail.tools.jwt import generate_vapid_keys

ENDPOINT = "https://fcm.googleapis.com/fcm/send/dcm-%s"
BROWSER_KEYS = {
    "p256dh": (
        "BGbhnoP_91U7oR59BaaSx0JnDv2oEooYnJRV2AbY5TBeKGCRCf0HcIJ9bOKchUCDH4cHYWo9"
        "SYDz3U-8vSxPL_A"
    ),
    "auth": "DJFdtAgZwrT6yYkUMgUqow",
}


@tagged("post_install", "-at_install")
class TestCommunityChannelNotify(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        private_key, public_key = generate_vapid_keys()
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("mail.web_push_vapid_private_key", private_key)
        params.set_param("mail.web_push_vapid_public_key", public_key)

        cls.channel = cls.env.ref("discuss_channel_zone.channel_canarias")
        cls.plain_channel = cls.env["discuss.channel"].create(
            {"name": "DCM Plain Channel", "channel_type": "channel"}
        )
        Users = cls.env["res.users"].with_context(no_reset_password=True)
        employee = cls.env.ref("base.group_user")

        def user(login, *groups):
            return Users.create(
                {
                    "name": login,
                    "login": login,
                    "email": "%s@example.com" % login,
                    "group_ids": [(6, 0, [employee.id, *[g.id for g in groups]])],
                }
            )

        cls.author = user("dcm_notify_author")
        cls.default_member = user("dcm_notify_default")
        cls.silent_member = user("dcm_notify_silent")
        cls.mentions_member = user("dcm_notify_mentions")
        cls.moderator = user(
            "dcm_notify_moderator",
            cls.env.ref("discuss_channel_moderation.group_moderation_manager"),
        )
        members = (
            cls.author + cls.default_member + cls.silent_member + cls.mentions_member
        )
        for channel in (cls.channel, cls.plain_channel):
            channel._add_members(users=members, post_joined_message=False)
            member_model = cls.env["discuss.channel.member"].sudo()
            member_model.search(
                [
                    ("channel_id", "=", channel.id),
                    ("partner_id", "=", cls.silent_member.partner_id.id),
                ]
            ).custom_notifications = "no_notif"
            member_model.search(
                [
                    ("channel_id", "=", channel.id),
                    ("partner_id", "=", cls.mentions_member.partner_id.id),
                ]
            ).custom_notifications = "mentions"
        cls.endpoints = {}
        for name, account in (
            ("author", cls.author),
            ("default", cls.default_member),
            ("silent", cls.silent_member),
            ("mentions", cls.mentions_member),
        ):
            cls.endpoints[name] = ENDPOINT % name
            cls.env["mail.push.device"].sudo().create(
                {
                    "endpoint": ENDPOINT % name,
                    "keys": json.dumps(BROWSER_KEYS),
                    "partner_id": account.partner_id.id,
                }
            )
        cls.guest = cls.env["mail.guest"].create({"name": "DCM Visitor"})
        cls.channel.sudo()._add_members(guests=cls.guest, post_joined_message=False)

    def _pushed(self, post):
        """Our test endpoints core's sender was asked to push to."""
        mine = set(self.endpoints.values())
        # A large MAX_DIRECT_PUSH keeps the send inline (no `mail.push`
        # queue), whatever other members the channel already has.
        with (
            patch.object(mail_thread, "push_to_end_point") as mocked,
            patch.object(mail_thread, "MAX_DIRECT_PUSH", 100000),
        ):
            post()
        return {
            call.kwargs["device"]["endpoint"]
            for call in mocked.call_args_list
            if call.kwargs["device"]["endpoint"] in mine
        }

    def _post(self, channel, body="Hello neighbours"):
        return (
            channel.with_user(self.author)
            .sudo()
            .message_post(
                body=body, message_type="comment", subtype_xmlid="mail.mt_comment"
            )
        )

    def test_published_message_pushes_to_default_members(self):
        pushed = self._pushed(lambda: self._post(self.channel))
        self.assertIn(self.endpoints["default"], pushed)

    def test_explicit_choices_are_kept(self):
        pushed = self._pushed(lambda: self._post(self.channel))
        self.assertNotIn(self.endpoints["silent"], pushed, "no_notif was overridden")
        self.assertNotIn(self.endpoints["mentions"], pushed, "mentions was overridden")
        self.assertNotIn(self.endpoints["author"], pushed, "the author was pushed")

    def test_no_member_rows_are_written(self):
        member = (
            self.env["discuss.channel.member"]
            .sudo()
            .search(
                [
                    ("channel_id", "=", self.channel.id),
                    ("partner_id", "=", self.default_member.partner_id.id),
                ]
            )
        )
        self._pushed(lambda: self._post(self.channel))
        self.assertFalse(member.custom_notifications)

    def test_non_community_channel_is_unchanged(self):
        pushed = self._pushed(lambda: self._post(self.plain_channel))
        self.assertEqual(pushed, set(), "a plain channel still notifies mentions only")

    def test_held_message_pushes_to_nobody_until_approved(self):
        guest_channel = (
            self.channel.with_user(self.env.ref("base.public_user"))
            .sudo()
            .with_context(guest=self.guest)
        )
        pushed = self._pushed(
            lambda: guest_channel.message_post(
                body="Held until approved",
                message_type="comment",
                subtype_xmlid="mail.mt_comment",
            )
        )
        self.assertEqual(pushed, set(), "a pending message was pushed")
        pending = (
            self.env["discuss.channel.pending.message"]
            .sudo()
            .search(
                [
                    ("channel_id", "=", self.channel.id),
                    ("guest_id", "=", self.guest.id),
                ],
                order="id desc",
                limit=1,
            )
        )
        self.assertTrue(pending, "the guest's message was not held")
        self.assertEqual(pending.state, "pending")

        pushed = self._pushed(
            lambda: pending.with_user(self.moderator).action_approve()
        )
        self.assertEqual(pending.state, "approved")
        self.assertIn(self.endpoints["default"], pushed)
        self.assertIn(self.endpoints["author"], pushed, "approval notifies everyone")
        self.assertNotIn(self.endpoints["silent"], pushed)
