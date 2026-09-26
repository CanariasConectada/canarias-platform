# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""No web push may arrive silently.

A web push cannot choose its sound; the phone plays its own. What silences
it is `silent: true`, or a `tag` without `renotify` -- the replacement of a
notification with the same tag is shown without sound. Every payload that
leaves the server therefore carries `silent: false`, `renotify: true` when it
has a tag (and only then: `renotify` without a tag makes the browser reject
the notification), and an Android vibration pattern.
"""

import json
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged
from odoo.tools import mute_logger

from odoo.addons.mail.models import mail_thread

from ..models.mail_thread import PUSH_VIBRATE_PATTERN, make_push_payload_audible
from .common import FCM_ENDPOINT, MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushAudible(MailPushGuestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()
        cls.device_guest_b = cls._create_device(
            FCM_ENDPOINT % "audible-guest-b", guest=cls.guest_b
        )
        cls.device_partner_author = cls._create_device(
            FCM_ENDPOINT % "audible-author", partner=cls.partner_author
        )

    def _assert_audible(self, payload, tagged_payload=False):
        options = payload["options"]
        self.assertIs(options["silent"], False)
        self.assertEqual(options["vibrate"], PUSH_VIBRATE_PATTERN)
        if tagged_payload:
            self.assertTrue(options["tag"])
            self.assertIs(options["renotify"], True)
        else:
            self.assertNotIn("renotify", options)

    def test_helper_contract(self):
        tagged_in = {"title": "t", "options": {"tag": "x", "silent": True}}
        tagged_out = make_push_payload_audible(tagged_in)
        self._assert_audible(tagged_out, tagged_payload=True)
        # Never mutates what it was given.
        self.assertIs(tagged_in["options"]["silent"], True)
        self.assertNotIn("renotify", tagged_in["options"])
        # `renotify` without a tag would make the browser reject the push.
        untagged = make_push_payload_audible({"options": {"renotify": True}})
        self.assertNotIn("renotify", untagged["options"])
        # A vibration pattern of its own (core's call invitation) is kept.
        call = make_push_payload_audible({"options": {"vibrate": [100, 50, 100]}})
        self.assertEqual(call["options"]["vibrate"], [100, 50, 100])
        # Idempotent.
        self.assertEqual(make_push_payload_audible(tagged_out), tagged_out)

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_guest_channel_push_is_audible(self):
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_partner(self.user_author, body="<p>hola</p>")
        pushed = dict(
            zip(
                self._pushed_endpoints(mocked_push),
                self._pushed_payloads(mocked_push),
                strict=True,
            )
        )
        self.assertIn(self.device_guest_b.endpoint, pushed)
        # Core's channel payload has no tag: each message is its own
        # notification, so no `renotify`.
        self._assert_audible(pushed[self.device_guest_b.endpoint])

    @mute_logger("odoo.addons.mail.models.mail_thread")
    def test_partner_channel_push_is_audible(self):
        # Core's own partner path; a channel notifies partners of mentions
        # only unless the member asked for everything.
        self.env["discuss.channel.member"].search(
            [
                ("channel_id", "=", self.channel.id),
                ("partner_id", "=", self.partner_author.id),
            ]
        ).custom_notifications = "all"
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self._post_as_guest(self.guest_b, body="<p>hola</p>")
        pushed = dict(
            zip(
                self._pushed_endpoints(mocked_push),
                self._pushed_payloads(mocked_push),
                strict=True,
            )
        )
        self.assertIn(self.device_partner_author.endpoint, pushed)
        self._assert_audible(pushed[self.device_partner_author.endpoint])

    def test_test_push_is_audible(self):
        with patch.object(mail_thread, "push_to_end_point") as mocked_push:
            self.env["mail.push.device"].with_user(self.user_author).cc_push_test()
        (payload,) = self._pushed_payloads(mocked_push)
        self._assert_audible(payload, tagged_payload=True)

    def test_queued_path_is_audible_too(self):
        """Over `MAX_DIRECT_PUSH` core queues `mail.push` rows for the cron."""
        with patch.object(mail_thread, "MAX_DIRECT_PUSH", 0):
            self.env["res.partner"]._web_push_send_notification(
                self.device_guest_b.sudo(),
                "private",
                "public",
                payload={"title": "t", "options": {"tag": "cc-x"}},
            )
        row = (
            self.env["mail.push"]
            .sudo()
            .search([("mail_push_device_id", "=", self.device_guest_b.id)])
        )
        self.assertTrue(row)
        self._assert_audible(json.loads(row[-1].payload), tagged_payload=True)
