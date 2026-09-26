# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The Discuss notification banner's state machine, EXECUTED in node.

`notification_banner_harness.js` runs the shipped
`static/src/backend/notification_banner.js` against fakes of the Push API
and of the server RPCs; every assertion is made here. A missing `node`
FAILS rather than skips: a skipped test would read as a passing one.
"""

import base64
import json
import os
import shutil
import subprocess
import tempfile

from odoo.tests import TransactionCase, tagged
from odoo.tools.misc import file_path

HARNESS = os.path.join(os.path.dirname(__file__), "notification_banner_harness.js")
SCRIPT = "discuss_community/static/src/backend/notification_banner.js"

KEY_BYTES = [(i * 37 + 11) % 256 for i in range(65)]
OLD_KEY_BYTES = [(i * 11 + 3) % 256 for i in range(65)]
KEY = base64.urlsafe_b64encode(bytes(KEY_BYTES)).rstrip(b"=").decode()

EP = "https://web.push.apple.com/%s"
MINE = EP % "mine"
FOREIGN = EP % "foreign"
FRESH = EP % "fresh"
FRESH2 = EP % "fresh2"

CASES = [
    # ---- silent check -------------------------------------------------
    {
        "name": "check_registered",
        "action": "check",
        "permission": "granted",
        "subscription": {"endpoint": MINE, "keyBytes": KEY_BYTES},
        "server": {"status": {MINE: "registered"}},
    },
    {
        "name": "check_granted_but_not_registered",
        "action": "check",
        "permission": "granted",
        "subscription": {"endpoint": MINE, "keyBytes": KEY_BYTES},
        "server": {"status": {MINE: "not_registered"}},
    },
    {
        "name": "check_granted_owned_by_other",
        "action": "check",
        "permission": "granted",
        "subscription": {"endpoint": FOREIGN, "keyBytes": KEY_BYTES},
        "server": {"status": {FOREIGN: "owned_by_other"}},
    },
    {
        "name": "check_granted_no_subscription",
        "action": "check",
        "permission": "granted",
    },
    {"name": "check_default_permission", "action": "check", "permission": "default"},
    {"name": "check_denied", "action": "check", "permission": "denied"},
    {
        "name": "check_ios_safari",
        "action": "check",
        "ios": True,
        "standalone": False,
        "support": {"PushManager": False, "Notification": False},
    },
    {
        "name": "check_unsupported",
        "action": "check",
        "support": {"PushManager": False},
    },
    {
        "name": "check_server_error",
        "action": "check",
        "permission": "granted",
        "subscription": {"endpoint": MINE, "keyBytes": KEY_BYTES},
        "server": {"fail": {"cc_push_status": "boom"}},
    },
    # ---- activate -----------------------------------------------------
    {
        "name": "activate_fresh",
        "action": "activate",
        "permission": "default",
        "grant": "granted",
        "newEndpoints": [FRESH],
        "server": {"status": {FRESH: "registered"}},
    },
    {
        "name": "activate_denied",
        "action": "activate",
        "permission": "default",
        "grant": "denied",
    },
    {
        "name": "activate_dismissed_prompt",
        "action": "activate",
        "permission": "default",
        "grant": "default",
    },
    {
        "name": "activate_claims_by_resubscribing",
        "action": "activate",
        "permission": "granted",
        "subscription": {"endpoint": FOREIGN, "keyBytes": KEY_BYTES},
        "newEndpoints": [FRESH],
        "server": {"status": {FOREIGN: "owned_by_other", FRESH: "registered"}},
    },
    {
        "name": "activate_still_owned_by_other",
        "action": "activate",
        "permission": "granted",
        "subscription": {"endpoint": FOREIGN, "keyBytes": KEY_BYTES},
        "newEndpoints": [FRESH],
        "server": {"status": {FOREIGN: "owned_by_other", FRESH: "owned_by_other"}},
    },
    {
        "name": "activate_rotated_key",
        "action": "activate",
        "permission": "granted",
        "subscription": {"endpoint": MINE, "keyBytes": OLD_KEY_BYTES},
        "newEndpoints": [FRESH2],
        "server": {"status": {FRESH2: "registered"}},
    },
    {
        "name": "activate_not_stored",
        "action": "activate",
        "permission": "granted",
        "newEndpoints": [FRESH],
        "server": {"status": {FRESH: "not_registered"}},
    },
    {
        "name": "activate_server_error",
        "action": "activate",
        "permission": "granted",
        "newEndpoints": [FRESH],
        "server": {"fail": {"/mail/push/subscribe": "too many devices"}},
    },
    {
        "name": "activate_no_key",
        "action": "activate",
        "permission": "granted",
        "server": {"vapidRoute": False},
    },
    {
        "name": "activate_rate_limited_test",
        "action": "activate",
        "permission": "granted",
        "subscription": {"endpoint": MINE, "keyBytes": KEY_BYTES},
        "server": {"status": {MINE: "registered"}, "test": {"status": "rate_limited"}},
    },
    {
        "name": "activate_ios_safari",
        "action": "activate",
        "ios": True,
        "support": {"PushManager": False, "Notification": False},
    },
    # ---- the component ------------------------------------------------
    {
        "name": "component_click_success",
        "action": "component",
        "permission": "default",
        "grant": "granted",
        "newEndpoints": [FRESH],
        "server": {"status": {FRESH: "registered"}},
    },
]


def _run():
    if not shutil.which("node"):
        raise RuntimeError(
            "discuss_community: `node` is required to execute the banner "
            "script under test and was not found on PATH."
        )
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"vapidKey": KEY, "cases": CASES}, handle)
        proc = subprocess.run(
            ["node", HARNESS, file_path(SCRIPT), input_path],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        raise AssertionError(
            "the harness produced no result (exit %s)\nstdout: %s\nstderr: %s"
            % (proc.returncode, proc.stdout[-2000:], proc.stderr[-2000:])
        ) from None
    if "harnessError" in result:
        raise AssertionError(
            "the banner script failed to load:\n%s" % result["harnessError"]
        )
    for name, case in result["cases"].items():
        if "harnessError" in case:
            raise AssertionError(f"case {name} crashed:\n{case['harnessError']}")
    return result


@tagged("post_install", "-at_install")
class TestNotificationBannerJS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        output = _run()
        cls.constants = output["constants"]
        cls.cases = output["cases"]

    def _state(self, name):
        return self.cases[name]["result"]

    def _log(self, name):
        return self.cases[name]["log"]

    def assertState(self, name, phase, reason=None):
        state = self._state(name)
        self.assertEqual((state["phase"], state["reason"]), (phase, reason), name)

    def test_uses_core_backend_worker(self):
        self.assertEqual(
            self.constants,
            {
                "url": "/web/service-worker.js",
                "scope": "/odoo",
                "storageKey": "mail.push.device_endpoint",
            },
        )

    # ------------------------------------------------------------------
    # Silent check: validates against the server, never trusts permission
    # ------------------------------------------------------------------

    def test_check_registered_hides_the_banner(self):
        self.assertState("check_registered", "hidden")
        self.assertIn("getRegistration:/odoo", self._log("check_registered"))

    def test_check_granted_is_not_enough(self):
        """The 2026-09-26 incident: permission granted, no server row."""
        self.assertState(
            "check_granted_but_not_registered", "inactive", "not_registered"
        )
        self.assertState("check_granted_owned_by_other", "inactive", "owned_by_other")
        self.assertState("check_granted_no_subscription", "inactive", "no_subscription")

    def test_check_never_prompts_nor_subscribes(self):
        for name, case in self.cases.items():
            if not name.startswith("check_"):
                continue
            self.assertFalse(
                [
                    entry
                    for entry in case["log"]
                    if entry.startswith(
                        ("requestPermission", "subscribe", "register:", "unsubscribe")
                    )
                ],
                f"{name}: the silent check touched the permission or the subscription",
            )

    def test_check_other_states(self):
        self.assertState("check_default_permission", "inactive", "no_permission")
        self.assertState("check_denied", "error", "denied")
        self.assertState("check_ios_safari", "error", "unsupported_ios")
        self.assertState("check_unsupported", "error", "unsupported")
        self.assertState("check_server_error", "error", "server")
        self.assertEqual(self._state("check_server_error")["message"], "boom")

    # ------------------------------------------------------------------
    # Activate and verify
    # ------------------------------------------------------------------

    def test_activate_asks_permission_first(self):
        """iOS only shows the prompt inside the gesture: first await."""
        self.assertEqual(self._log("activate_fresh")[0], "requestPermission")

    def test_activate_fresh_registers_then_verifies_then_tests(self):
        self.assertState("activate_fresh", "success", "tested")
        log = self._log("activate_fresh")
        self.assertEqual(
            log,
            [
                "requestPermission",
                "register:/web/service-worker.js|/odoo",
                "rpc:/mail/push/vapid",
                "subscribe:%s" % FRESH,
                "rpc:/mail/push/subscribe",
                "subscribed-endpoint:%s|backend" % FRESH,
                "rpc:cc_push_status",
                "rpc:cc_push_test",
            ],
        )
        self.assertEqual(
            self.cases["activate_fresh"]["storage"],
            {"mail.push.device_endpoint": FRESH},
        )

    def test_activate_denied_or_dismissed(self):
        self.assertState("activate_denied", "error", "denied")
        self.assertState("activate_dismissed_prompt", "inactive", "no_permission")
        for name in ("activate_denied", "activate_dismissed_prompt"):
            self.assertEqual(self._log(name), ["requestPermission"], name)

    def test_activate_owned_by_other_resubscribes_to_a_fresh_endpoint(self):
        self.assertState("activate_claims_by_resubscribing", "success", "tested")
        log = self._log("activate_claims_by_resubscribing")
        self.assertIn("unsubscribe:%s" % FOREIGN, log)
        self.assertIn("subscribed-endpoint:%s|backend" % FRESH, log)
        self.assertLess(
            log.index("unsubscribe:%s" % FOREIGN), log.index("subscribe:%s" % FRESH)
        )
        self.assertEqual(log[-1], "rpc:cc_push_test")

    def test_activate_gives_up_after_one_resubscription(self):
        self.assertState("activate_still_owned_by_other", "error", "owned_by_other")
        log = self._log("activate_still_owned_by_other")
        self.assertEqual(len([e for e in log if e.startswith("subscribe:")]), 1)
        self.assertNotIn("rpc:cc_push_test", log)

    def test_activate_replaces_a_subscription_made_with_another_key(self):
        self.assertState("activate_rotated_key", "success", "tested")
        log = self._log("activate_rotated_key")
        self.assertIn("unsubscribe:%s" % MINE, log)
        self.assertIn("subscribed-endpoint:%s|backend" % FRESH2, log)

    def test_activate_failures(self):
        self.assertState("activate_not_stored", "error", "not_stored")
        self.assertNotIn("rpc:cc_push_test", self._log("activate_not_stored"))
        self.assertState("activate_server_error", "error", "server")
        self.assertEqual(
            self._state("activate_server_error")["message"], "too many devices"
        )
        self.assertState("activate_no_key", "error", "no_key")
        self.assertState("activate_ios_safari", "error", "unsupported_ios")
        self.assertEqual(self._log("activate_ios_safari"), [])

    def test_activate_rate_limited_test_is_still_a_success(self):
        self.assertState("activate_rate_limited_test", "success")

    # ------------------------------------------------------------------
    # Component
    # ------------------------------------------------------------------

    def test_component_click(self):
        result = self._state("component_click_success")
        self.assertEqual(result["phaseRightAfterClick"], "working")
        self.assertEqual(
            result["logRightAfterClick"],
            ["requestPermission"],
            "requestPermission must be called synchronously from the click",
        )
        self.assertEqual(result["phaseAfter"], "success")
        self.assertTrue(result["visibleAfter"])
        self.assertEqual(result["delays"], [6000])
        self.assertEqual(result["phaseAfterTimer"], "hidden")
        self.assertFalse(result["visibleAfterTimer"])
