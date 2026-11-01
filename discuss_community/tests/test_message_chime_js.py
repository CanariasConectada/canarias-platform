# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Which Discuss messages ring the foreground chime, EXECUTED in node.

The rule mirrors who the server pushes, so the open app sounds for exactly
the messages the closed app buzzes for. A missing `node` fails, never skips.
"""

import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

HARNESS = os.path.join(os.path.dirname(__file__), "message_chime_harness.js")
SCRIPT = "discuss_community/static/src/backend/message_chime_rules.js"

# A member of a chat, someone else wrote, nothing special.
BASE = {"isMember": True, "channelType": "chat"}


def _channel(**facts):
    return dict({"isMember": True, "channelType": "channel"}, **facts)


CASES = {
    # Chats and groups ring by default.
    "chat": (dict(BASE), True),
    "group": (dict(BASE, channelType="group"), True),
    # The listener's own message, never.
    "own_message": (dict(BASE, selfAuthored=True), False),
    # The conversation on screen and focused, never.
    "in_view": (dict(BASE, inView=True), False),
    "silent_post": (dict(BASE, silent=True), False),
    "system_notification": (dict(BASE, isNotification=True), False),
    "not_a_member": (dict(BASE, isMember=False), False),
    "member_muted": (dict(BASE, memberMuted=True), False),
    "busy": (dict(BASE, busy=True), False),
    # Channels follow the notification settings.
    "channel_default_not_mentioned": (_channel(), False),
    "channel_default_mentioned": (_channel(mentioned=True), True),
    "channel_member_all": (_channel(memberSetting="all"), True),
    "channel_user_all": (_channel(userSetting="all"), True),
    "channel_member_no_notif": (
        _channel(memberSetting="no_notif", mentioned=True),
        False,
    ),
    "channel_user_no_notif": (_channel(userSetting="no_notif", mentioned=True), False),
    # Community channels: a member without a setting hears everything...
    "community_unset": (_channel(communityChannel=True), True),
    # ...but an explicit member choice wins, as on the server.
    "community_member_mentions": (
        _channel(communityChannel=True, memberSetting="mentions"),
        False,
    ),
    "community_member_no_notif": (
        _channel(communityChannel=True, memberSetting="no_notif"),
        False,
    ),
    "community_user_no_notif": (
        _channel(communityChannel=True, userSetting="no_notif"),
        False,
    ),
    "community_own_message": (
        _channel(communityChannel=True, selfAuthored=True),
        False,
    ),
}


@tagged("post_install", "-at_install")
class TestMessageChimeJS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not shutil.which("node"):
            raise RuntimeError(
                "discuss_community: `node` is required to run the chime rules."
            )
        with tempfile.TemporaryDirectory() as tmp:
            input_path = os.path.join(tmp, "input.json")
            with open(input_path, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "cases": [
                            {"name": n, "facts": f} for n, (f, _e) in CASES.items()
                        ]
                    },
                    handle,
                )
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
                "the chime rules harness produced no result (exit %s)\n%s\n%s"
                % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
            ) from None
        if "harnessError" in result:
            raise AssertionError(result["harnessError"])
        cls.observed = result["cases"]

    def test_rules(self):
        for name, (_facts, expected) in CASES.items():
            with self.subTest(case=name):
                self.assertIs(self.observed[name], expected)
