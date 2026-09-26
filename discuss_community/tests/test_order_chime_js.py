# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""A chat chime must never swallow a new-order chime.

`order_chime_harness.js` loads the shipped chime.js (mail_push_guest),
message_chime.js (this module) and order_push_chime.js
(website_sale_merchant_alert) together, as the backend bundle does, and
plays chat messages and order pushes on a fake clock. Reproduced before the
fix: the order played through the chat throttle and was dropped when a chat
message had rung less than 2 s earlier.
"""

import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

HARNESS = os.path.join(os.path.dirname(__file__), "order_chime_harness.js")
PATHS = {
    "chime": "mail_push_guest/static/src/js/chime.js",
    "rules": "discuss_community/static/src/backend/message_chime_rules.js",
    "message": "discuss_community/static/src/backend/message_chime.js",
    "order": "website_sale_merchant_alert/static/src/js/order_push_chime.js",
}
CASES = [
    {
        "name": "chat_then_order",
        "steps": [{"at": 1000, "chat": True}, {"at": 1500, "order": True}],
    },
    {
        "name": "order_then_chat",
        "steps": [{"at": 1000, "order": True}, {"at": 1200, "chat": True}],
    },
    {
        "name": "two_orders",
        "steps": [
            {"at": 1000, "order": True},
            {"at": 1800, "order": True},
            {"at": 3100, "order": True},
        ],
    },
    {
        "name": "two_chats",
        "steps": [{"at": 1000, "chat": True}, {"at": 1800, "chat": True}],
    },
]


@tagged("post_install", "-at_install")
class TestOrderChimeJS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not shutil.which("node"):
            raise RuntimeError(
                "discuss_community: `node` is required to run the chimes."
            )
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "input.json")
            with open(input_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "paths": {k: file_path(v) for k, v in PATHS.items()},
                        "cases": CASES,
                    },
                    handle,
                )
            proc = subprocess.run(
                ["node", HARNESS, input_path],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        try:
            result = json.loads(proc.stdout)
        except ValueError:
            raise AssertionError(
                "the order chime harness produced no result (exit %s)\n%s\n%s"
                % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
            ) from None
        if "harnessError" in result:
            raise AssertionError(result["harnessError"])
        cls.played = {
            name: [(p["kind"], p["at"]) for p in plays]
            for name, plays in result["cases"].items()
        }

    def test_an_order_right_after_a_chat_message_still_chimes(self):
        self.assertEqual(
            self.played["chat_then_order"], [("message", 1000), ("order", 1500)]
        )

    def test_a_chat_message_right_after_an_order_still_chimes(self):
        self.assertEqual(
            self.played["order_then_chat"], [("order", 1000), ("message", 1200)]
        )

    def test_two_orders_within_two_seconds_chime_once(self):
        self.assertEqual(self.played["two_orders"], [("order", 1000), ("order", 3100)])

    def test_chat_burst_still_throttled(self):
        self.assertEqual(self.played["two_chats"], [("message", 1000)])
