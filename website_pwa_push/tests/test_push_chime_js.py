# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The website page's chime for a push the worker has shown, EXECUTED."""

import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

HARNESS = os.path.join(os.path.dirname(__file__), "push_chime_harness.js")
SCRIPT = "website_pwa_push/static/src/js/push_chime.js"

CHANNEL = {"model": "discuss.channel", "res_id": 7}
CASES = [
    {
        "name": "other_author",
        "data": dict(CHANNEL, author_partner_id=5),
        "persona": {"partnerId": 3},
    },
    {
        "name": "own_partner",
        "data": dict(CHANNEL, author_partner_id=3),
        "persona": {"partnerId": 3},
    },
    {
        "name": "own_guest",
        "data": dict(CHANNEL, author_guest_id=9),
        "persona": {"guestId": 9},
    },
    # Unknown author ids (0/false) never match an anonymous page.
    {"name": "no_author_ids", "data": CHANNEL, "persona": {}},
    {
        "name": "conversation_in_view",
        "data": CHANNEL,
        "focused": True,
        "chatChannelId": 7,
    },
    {
        "name": "other_conversation_on_screen",
        "data": CHANNEL,
        "focused": True,
        "chatChannelId": 8,
    },
    {
        "name": "typing_in_support_frame",
        "data": CHANNEL,
        "focused": True,
        "activeIframe": True,
    },
    {
        "name": "android_granted",
        "data": CHANNEL,
        "android": True,
        "permission": "granted",
    },
    {"name": "other_message_type", "data": CHANNEL, "type": "something-else"},
]


@tagged("post_install", "-at_install")
class TestPushChimeJS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not shutil.which("node"):
            raise RuntimeError(
                "website_pwa_push: `node` is required to run push_chime.js."
            )
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "input.json")
            with open(input_path, "w", encoding="utf-8") as handle:
                json.dump({"cases": CASES}, handle)
            proc = subprocess.run(
                ["node", HARNESS, file_path(SCRIPT), input_path],
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
        try:
            result = json.loads(proc.stdout)
        except ValueError:
            raise AssertionError(
                "the push chime harness produced no result (exit %s)\n%s\n%s"
                % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
            ) from None
        if "harnessError" in result:
            raise AssertionError(result["harnessError"])
        cls.cases = result["cases"]

    def test_someone_elses_message_chimes(self):
        self.assertTrue(self.cases["other_author"]["returned"])
        self.assertTrue(self.cases["no_author_ids"]["returned"])

    def test_own_message_never_chimes(self):
        for name in ("own_partner", "own_guest"):
            with self.subTest(case=name):
                self.assertTrue(self.cases[name]["ring"]["ownMessage"])
                self.assertFalse(self.cases[name]["returned"])

    def test_conversation_in_view_does_not_chime(self):
        self.assertTrue(self.cases["conversation_in_view"]["ring"]["inView"])
        self.assertTrue(self.cases["typing_in_support_frame"]["ring"]["inView"])
        self.assertFalse(self.cases["other_conversation_on_screen"]["ring"]["inView"])

    def test_android_and_foreign_messages_are_left_alone(self):
        for name in ("android_granted", "other_message_type"):
            with self.subTest(case=name):
                self.assertFalse(self.cases[name]["returned"])
                self.assertIsNone(self.cases[name]["ring"])
