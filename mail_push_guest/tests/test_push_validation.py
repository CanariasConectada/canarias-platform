# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""`cc_push_status` and `cc_push_test`: the server half of the Discuss banner
that VALIDATES notifications instead of trusting `Notification.permission`."""

import json
from datetime import timedelta
from unittest.mock import patch

from freezegun import freeze_time

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged

from odoo.addons.mail.models import mail_thread
from odoo.addons.mail_push_guest.models.mail_push_device import (
    PUSH_STATUS_NOT_REGISTERED,
    PUSH_STATUS_OWNED_BY_OTHER,
    PUSH_STATUS_REGISTERED,
    PUSH_TEST_INTERVAL_SECONDS,
    PUSH_TEST_NO_DEVICE,
    PUSH_TEST_RATE_LIMITED,
    PUSH_TEST_SENT,
    PUSH_TEST_TITLE,
)

from .common import FCM_ENDPOINT, MailPushGuestMixin


@tagged("post_install", "-at_install")
class TestPushStatus(MailPushGuestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()
        cls.user_other = cls.env["res.users"].create(
            {
                "name": "Other Account",
                "login": "mpg_other",
                "email": "mpg_other@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def _status_as(self, user, endpoint):
        return self.env["mail.push.device"].with_user(user).cc_push_status(endpoint)

    def test_status_registered(self):
        endpoint = FCM_ENDPOINT % "status-mine"
        self._create_device(endpoint, partner=self.partner_author)
        self.assertEqual(
            self._status_as(self.user_author, endpoint), PUSH_STATUS_REGISTERED
        )

    def test_status_not_registered(self):
        self.assertEqual(
            self._status_as(self.user_author, FCM_ENDPOINT % "status-nobody"),
            PUSH_STATUS_NOT_REGISTERED,
        )
        for garbage in (None, "", 42, {"endpoint": "x"}, "x" * 600):
            self.assertEqual(
                self._status_as(self.user_author, garbage),
                PUSH_STATUS_NOT_REGISTERED,
                "Malformed input must not raise and must not be 'registered'",
            )

    def test_status_owned_by_other_partner(self):
        endpoint = FCM_ENDPOINT % "status-other"
        self._create_device(endpoint, partner=self.user_other.partner_id)
        status = self._status_as(self.user_author, endpoint)
        self.assertEqual(status, PUSH_STATUS_OWNED_BY_OTHER)
        # Nothing but the status string leaves the method: no owner id/name.
        self.assertIsInstance(status, str)
        self.assertNotIn(str(self.user_other.partner_id.id), status)

    def test_status_owned_by_foreign_guest(self):
        endpoint = FCM_ENDPOINT % "status-guest"
        self._create_device(endpoint, guest=self.guest_b)
        self.assertEqual(
            self._status_as(self.user_author, endpoint), PUSH_STATUS_OWNED_BY_OTHER
        )

    def test_status_claimable_guest_row_is_not_a_conflict(self):
        """The guest -> login upgrade: the row will be carried over."""
        endpoint = FCM_ENDPOINT % "status-upgrade"
        self._create_device(endpoint, guest=self.guest_b)
        with patch.object(
            type(self.env["mail.push.device"]),
            "_current_guest",
            lambda model: self.guest_b,
        ):
            self.assertEqual(
                self._status_as(self.user_author, endpoint),
                PUSH_STATUS_NOT_REGISTERED,
            )


@tagged("post_install", "-at_install")
class TestPushTest(MailPushGuestMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()
        cls.user_other = cls.env["res.users"].create(
            {
                "name": "Other Account",
                "login": "mpg_other_test",
                "email": "mpg_other_test@example.com",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )
        cls.mine = cls._create_device(
            FCM_ENDPOINT % "test-mine", partner=cls.partner_author
        )
        cls.other = cls._create_device(
            FCM_ENDPOINT % "test-other", partner=cls.user_other.partner_id
        )
        cls.guest_device = cls._create_device(
            FCM_ENDPOINT % "test-guest", guest=cls.guest_b
        )

    def _test_as(self, user):
        return self.env["mail.push.device"].with_user(user).cc_push_test()

    def test_push_test_targets_only_own_devices(self):
        with patch.object(mail_thread, "push_to_end_point") as mocked:
            result = self._test_as(self.user_author)
        self.assertEqual(result, {"status": PUSH_TEST_SENT, "devices": 1})
        self.assertEqual(
            self._pushed_endpoints(mocked),
            [self.mine.endpoint],
            "The test push reached a device that is not the caller's",
        )
        payload = self._pushed_payloads(mocked)[0]
        self.assertEqual(payload["title"], PUSH_TEST_TITLE)
        self.assertIn("✓", payload["options"]["body"])

    def test_push_test_rate_limited_per_user(self):
        start = fields.Datetime.now()
        with patch.object(mail_thread, "push_to_end_point") as mocked:
            with freeze_time(start):
                first = self._test_as(self.user_author)
            with freeze_time(start + timedelta(seconds=PUSH_TEST_INTERVAL_SECONDS - 5)):
                second = self._test_as(self.user_author)
                # Another user is not throttled by the first one.
                other = self._test_as(self.user_other)
            with freeze_time(start + timedelta(seconds=PUSH_TEST_INTERVAL_SECONDS + 5)):
                third = self._test_as(self.user_author)
        self.assertEqual(first["status"], PUSH_TEST_SENT)
        self.assertEqual(second, {"status": PUSH_TEST_RATE_LIMITED})
        self.assertEqual(other["status"], PUSH_TEST_SENT)
        self.assertEqual(third["status"], PUSH_TEST_SENT)
        self.assertEqual(
            self._pushed_endpoints(mocked),
            [self.mine.endpoint, self.other.endpoint, self.mine.endpoint],
        )

    def test_push_test_without_device(self):
        user = self.env["res.users"].create(
            {
                "name": "No Device",
                "login": "mpg_nodevice",
                "email": "mpg_nodevice@example.com",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        with patch.object(mail_thread, "push_to_end_point") as mocked:
            self.assertEqual(self._test_as(user), {"status": PUSH_TEST_NO_DEVICE})
        mocked.assert_not_called()


@tagged("post_install", "-at_install")
class TestPushValidationRpc(MailPushGuestMixin, HttpCase):
    """Both methods are reachable over `call_kw` by a NON-system user.

    `mail.push.device` has no ACL for ordinary users; the methods sudo
    internally, like core's `register_devices`, so the banner works for
    guests, merchants and staff alike.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_push_fixtures()
        cls.user_author.password = "mpg_author_pwd"

    def _call_kw(self, method, **kwargs):
        return self.make_jsonrpc_request(
            f"/web/dataset/call_kw/mail.push.device/{method}",
            {
                "model": "mail.push.device",
                "method": method,
                "args": [],
                "kwargs": kwargs,
            },
        )

    def test_status_and_test_over_call_kw(self):
        endpoint = FCM_ENDPOINT % "rpc-mine"
        self.authenticate(self.user_author.login, "mpg_author_pwd")
        self.assertEqual(
            self._call_kw("cc_push_status", endpoint=endpoint),
            PUSH_STATUS_NOT_REGISTERED,
        )
        self._create_device(endpoint, partner=self.partner_author)
        self.assertEqual(
            self._call_kw("cc_push_status", endpoint=endpoint),
            PUSH_STATUS_REGISTERED,
        )
        with patch.object(mail_thread, "push_to_end_point") as mocked:
            result = self._call_kw("cc_push_test")
        self.assertEqual(result["status"], PUSH_TEST_SENT)
        self.assertEqual(
            [json.loads(c.kwargs["payload"])["title"] for c in mocked.call_args_list],
            [PUSH_TEST_TITLE],
        )
