# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The foreground chime, EXECUTED in node (see `chime_harness.js`).

A missing `node` fails loudly instead of skipping, as in website_pwa_push's
service worker suite: the Doodba image the CI runs in ships it.
"""

import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import TransactionCase, tagged

HERE = os.path.dirname(__file__)
HARNESS = os.path.join(HERE, "chime_harness.js")
CHIME = os.path.join(HERE, os.pardir, "static", "src", "js", "chime.js")

KEY = "mail.user_setting.message_sound"


def _run(cases):
    if not shutil.which("node"):
        raise RuntimeError(
            "mail_push_guest: `node` is required to run the chime under test."
        )
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"cases": cases}, handle)
        proc = subprocess.run(
            ["node", HARNESS, CHIME, input_path],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(
            "the chime harness produced no result (exit %s)\nstdout: %s\nstderr: %s"
            % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
        ) from None
    if "harnessError" in result:
        raise AssertionError("the chime failed to run:\n%s" % result["harnessError"])
    return result


@tagged("post_install", "-at_install")
class TestChimeJS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.result = _run(
            [
                # Throttle: a burst within 2 s is one ding; after 2 s, again.
                {
                    "name": "burst",
                    "steps": [
                        {"at": 1000},
                        {"at": 1500},
                        {"at": 2999},
                        {"at": 3000},
                        {"at": 3100},
                    ],
                },
                # Own message and a conversation in view never ring, and do
                # not consume the throttle slot either.
                {
                    "name": "own_and_in_view",
                    "steps": [
                        {"at": 1000, "ring": {"ownMessage": True}},
                        {"at": 1100, "ring": {"inView": True}},
                        {"at": 1200},
                    ],
                },
                {
                    "name": "muted_by_core_setting",
                    "storage": {KEY: "false"},
                    "steps": [{"at": 1000}],
                },
                {
                    "name": "mute_toggle",
                    "steps": [
                        {"mute": True},
                        {"at": 1000},
                        {"mute": False},
                        {"at": 1100},
                    ],
                },
                {
                    "name": "storage_blocked",
                    "storage": "throws",
                    "steps": [{"mute": True}, {"at": 1000}],
                },
                {
                    "name": "shared",
                    "kind": "shared",
                    "steps": [
                        {"at": 1000, "doc": 1},
                        {"at": 1200, "doc": 2},
                        {"at": 3300, "doc": 2},
                        {"at": 3400, "doc": 1},
                    ],
                },
                # A stored time far in the future does not mute forever.
                {
                    "name": "future_stamp",
                    "storage": {"mail_push_guest.chime_last_at": "999999999"},
                    "steps": [{"at": 1000}],
                },
                {"name": "player_ogg", "kind": "player", "ogg": True},
                {"name": "player_mp3", "kind": "player", "ogg": False},
                {
                    "name": "player_refused",
                    "kind": "player",
                    "ogg": True,
                    "rejects": True,
                },
                {
                    "name": "view_focused",
                    "kind": "inView",
                    "visibility": "visible",
                    "focus": True,
                },
                {
                    "name": "view_blurred",
                    "kind": "inView",
                    "visibility": "visible",
                    "focus": False,
                },
                {
                    "name": "view_hidden",
                    "kind": "inView",
                    "visibility": "hidden",
                    "focus": True,
                },
            ]
        )
        cls.cases = cls.result["cases"]

    def test_constants(self):
        self.assertEqual(self.result["constants"]["interval"], 2000)
        # Core's key: one switch for Discuss and the website chat.
        self.assertEqual(self.result["constants"]["key"], KEY)

    def test_at_most_one_chime_every_two_seconds(self):
        burst = self.cases["burst"]
        self.assertEqual(burst["rang"], [True, False, False, True, False])
        self.assertEqual(burst["played"], 2)

    def test_the_throttle_holds_across_documents_of_the_origin(self):
        """Two tabs, or the page and the support chat framed in it."""
        self.assertEqual(self.cases["shared"]["rang"], [True, False, True, False])
        self.assertEqual(self.cases["future_stamp"]["rang"], [True])

    def test_never_for_own_message_nor_the_conversation_in_view(self):
        observed = self.cases["own_and_in_view"]
        self.assertEqual(observed["rang"], [False, False, True])
        self.assertEqual(observed["played"], 1)

    def test_core_message_sound_setting_mutes(self):
        self.assertEqual(self.cases["muted_by_core_setting"]["rang"], [False])
        self.assertEqual(self.cases["muted_by_core_setting"]["played"], 0)

    def test_toggle_writes_core_setting_and_defaults_on(self):
        observed = self.cases["mute_toggle"]
        self.assertEqual(observed["rang"], [False, True])
        self.assertFalse(observed["muted"])
        self.assertNotIn(KEY, observed["storage"])

    def test_blocked_storage_neither_throws_nor_forgets_the_page_choice(self):
        observed = self.cases["storage_blocked"]
        # Muted for this page even though nothing could be stored.
        self.assertEqual(observed["rang"], [False])
        self.assertTrue(observed["muted"])

    def test_player_reuses_one_element_and_picks_the_format(self):
        ogg = self.cases["player_ogg"]
        self.assertEqual(ogg["created"], 1)
        self.assertEqual(ogg["plays"], 2)
        self.assertEqual(ogg["currentTime"], 0)
        self.assertEqual(ogg["src"], "/mail/static/src/audio/new-message.ogg")
        self.assertEqual(
            self.cases["player_mp3"]["src"], "/mail/static/src/audio/new-message.mp3"
        )
        # An autoplay refusal is swallowed (the harness fails on an
        # unhandled rejection).
        self.assertEqual(self.cases["player_refused"]["plays"], 2)

    def test_in_view_needs_visible_and_focused(self):
        self.assertTrue(self.cases["view_focused"]["inView"])
        self.assertFalse(self.cases["view_blurred"]["inView"])
        self.assertFalse(self.cases["view_hidden"]["inView"])
