# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The page script's push orchestration, EXECUTED.

Same technique as `test_service_worker_js.py`: the shipped file runs in
`node` (`page_script_harness.js`) against fakes of ServiceWorkerRegistration,
PushManager, subscriptions and worker state changes, and every assertion is
made here on what the harness observed. What is under test is the part no
Python test can see: which registration a subscription goes to, the VAPID
rotation branch, the bookkeeping core's web client reads, `whenActive` and the
tap-to-open listener.

A missing `node` FAILS rather than skips, for the reason given in
`test_service_worker_js.py`.
"""

import base64
import json
import os
import re
import shutil
import subprocess
import tempfile

from odoo.tests import TransactionCase, tagged
from odoo.tools import file_open
from odoo.tools.misc import file_path

HARNESS = os.path.join(os.path.dirname(__file__), "page_script_harness.js")
PAGE_SCRIPT = "website_pwa_push/static/src/js/pwa_push.js"
CORE_WEBCLIENT = "mail/static/src/webclient/web/webclient.js"

KEY_BYTES = [(i * 37 + 11) % 256 for i in range(65)]
OLD_KEY_BYTES = [(i * 11 + 3) % 256 for i in range(65)]
KEY = base64.urlsafe_b64encode(bytes(KEY_BYTES)).rstrip(b"=").decode()

NEW_ENDPOINT = "https://fcm.googleapis.com/fcm/send/new"
OLD_ENDPOINT = "https://fcm.googleapis.com/fcm/send/old"
WEBSITE_ENDPOINT = "https://fcm.googleapis.com/fcm/send/website"

BACKEND_ACTIVE = {"scope": "/odoo", "worker": "active", "newEndpoint": NEW_ENDPOINT}
WEBSITE_WITH_SUB = {
    "scope": "/",
    "worker": "active",
    "newEndpoint": WEBSITE_ENDPOINT,
    "subscription": {"endpoint": WEBSITE_ENDPOINT, "keyBytes": KEY_BYTES},
}
WEBSITE_EMPTY = {"scope": "/", "worker": "active", "newEndpoint": WEBSITE_ENDPOINT}

CASES = [
    {"name": "constants", "scenario": "constants"},
    {
        "name": "backend_fresh",
        "scenario": "subscribe",
        "target": "backend",
        "backend": BACKEND_ACTIVE,
        "website": WEBSITE_WITH_SUB,
    },
    {
        "name": "backend_rotated_key",
        "scenario": "subscribe",
        "target": "backend",
        "backend": dict(
            BACKEND_ACTIVE,
            subscription={"endpoint": OLD_ENDPOINT, "keyBytes": OLD_KEY_BYTES},
        ),
    },
    {
        "name": "backend_same_key",
        "scenario": "subscribe",
        "target": "backend",
        "backend": dict(
            BACKEND_ACTIVE,
            subscription={"endpoint": OLD_ENDPOINT, "keyBytes": KEY_BYTES},
        ),
    },
    {
        "name": "backend_installing",
        "scenario": "subscribe",
        "target": "backend",
        "backend": dict(BACKEND_ACTIVE, worker="installing"),
        "activateAfterRegister": True,
    },
    {
        "name": "website_target",
        "scenario": "subscribe",
        "target": "website",
        "website": WEBSITE_EMPTY,
    },
    {"name": "deferred_target", "scenario": "subscribe", "target": "deferred"},
    {
        "name": "registration_backend",
        "scenario": "pushRegistration",
        "target": "backend",
        "backend": BACKEND_ACTIVE,
        "website": WEBSITE_EMPTY,
    },
    {
        "name": "registration_website",
        "scenario": "pushRegistration",
        "target": "website",
        "backend": BACKEND_ACTIVE,
        "website": WEBSITE_EMPTY,
    },
    {
        "name": "active_now",
        "scenario": "whenActive",
        "registration": {"scope": "/odoo", "worker": "active"},
    },
    {
        "name": "installing_then_activated",
        "scenario": "whenActive",
        "registration": {"scope": "/odoo", "worker": "installing"},
        "transition": "activated",
    },
    {
        "name": "waiting_then_activated",
        "scenario": "whenActive",
        "registration": {"scope": "/odoo", "worker": "waiting"},
        "transition": "activated",
    },
    {
        "name": "installing_then_redundant",
        "scenario": "whenActive",
        "registration": {"scope": "/odoo", "worker": "installing"},
        "transition": "redundant",
    },
    {
        "name": "no_worker",
        "scenario": "whenActive",
        "registration": {"scope": "/odoo"},
    },
    {
        "name": "open_channel",
        "scenario": "openChannel",
        "message": {"action": "OPEN_CHANNEL", "data": {"id": 7, "joinCall": False}},
    },
    {
        "name": "open_channel_call",
        "scenario": "openChannel",
        "message": {"action": "OPEN_CHANNEL", "data": {"id": 7, "joinCall": True}},
    },
    {
        "name": "open_channel_traversal",
        "scenario": "openChannel",
        "message": {"action": "OPEN_CHANNEL", "data": {"id": "7/../../x"}},
    },
    {
        "name": "other_message",
        "scenario": "openChannel",
        "message": {"type": "notification-display-request", "payload": {}},
    },
]


def _run():
    if not shutil.which("node"):
        raise RuntimeError(
            "website_pwa_push: `node` is required to execute the page script "
            "under test and was not found on PATH."
        )
    with tempfile.TemporaryDirectory() as tmp:
        input_path = os.path.join(tmp, "input.json")
        with open(input_path, "w", encoding="utf-8") as handle:
            json.dump({"vapidKey": KEY, "cases": CASES}, handle)
        proc = subprocess.run(
            ["node", HARNESS, file_path(PAGE_SCRIPT), input_path],
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
            "the page script failed to load:\n%s" % result["harnessError"]
        )
    for name, case in result["cases"].items():
        if "harnessError" in case:
            raise AssertionError(f"case {name} crashed:\n{case['harnessError']}")
    return result["cases"]


@tagged("post_install", "-at_install")
class TestPageScriptJS(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cases = _run()

    def _routes(self, case):
        return [call["route"] for call in case["rpc"]]

    def _rpc(self, case, route):
        return next(call["params"] for call in case["rpc"] if call["route"] == route)

    # ------------------------------------------------------------------
    # subscribe()
    # ------------------------------------------------------------------

    def test_backend_subscription_goes_to_core_registration(self):
        case = self.cases["backend_fresh"]
        self.assertEqual(
            case["register"], [{"url": "/web/service-worker.js", "scope": "/odoo"}]
        )
        self.assertEqual(case["readyUsed"], 0, "the website worker must not be used")
        self.assertEqual(len(case["subscribeCalls"]), 1)
        call = case["subscribeCalls"][0]
        self.assertEqual(call["registration"], "backend")
        self.assertTrue(call["userVisibleOnly"])
        self.assertEqual(
            call["keyBytes"], KEY_BYTES, "the key must be decoded to bytes"
        )
        params = self._rpc(case, "/mail/push/subscribe")
        self.assertEqual(params["endpoint"], NEW_ENDPOINT)
        self.assertEqual(params["worker"], "backend")
        self.assertEqual(params["vapid_public_key"], KEY)
        self.assertEqual(case["result"], {"state": "resolved", "value": True})

    def test_backend_subscription_retires_the_website_one(self):
        """Double notifications: the same browser subscribed on both workers
        gets every message twice."""
        case = self.cases["backend_fresh"]
        self.assertEqual(case["getRegistration"], ["/"])
        self.assertEqual(case["unsubscribed"], [WEBSITE_ENDPOINT])
        self.assertEqual(
            self._routes(case),
            ["/mail/push/vapid", "/mail/push/subscribe", "/mail/push/unsubscribe"],
            "the backend row is stored BEFORE the website one is dropped",
        )
        self.assertEqual(
            self._rpc(case, "/mail/push/unsubscribe"), {"endpoint": WEBSITE_ENDPOINT}
        )

    def test_rotated_vapid_key_unsubscribes_then_resubscribes(self):
        case = self.cases["backend_rotated_key"]
        self.assertEqual(case["unsubscribed"], [OLD_ENDPOINT])
        self.assertEqual(len(case["subscribeCalls"]), 1)
        self.assertEqual(case["subscribeCalls"][0]["keyBytes"], KEY_BYTES)
        self.assertEqual(
            self._rpc(case, "/mail/push/subscribe")["endpoint"], NEW_ENDPOINT
        )

    def test_current_key_reuses_the_subscription(self):
        case = self.cases["backend_same_key"]
        self.assertEqual(case["subscribeCalls"], [])
        self.assertEqual(case["unsubscribed"], [])
        self.assertEqual(
            self._rpc(case, "/mail/push/subscribe")["endpoint"], OLD_ENDPOINT
        )
        self.assertEqual(
            case["storage"], {}, "core's bookkeeping is only for new subscriptions"
        )
        self.assertNotIn("/mail/push/unsubscribe", self._routes(case))

    def test_backend_waits_for_a_freshly_installed_worker(self):
        case = self.cases["backend_installing"]
        self.assertEqual(case["result"], {"state": "resolved", "value": True})
        self.assertEqual(len(case["subscribeCalls"]), 1)

    def test_website_subscription_uses_the_controlling_worker(self):
        case = self.cases["website_target"]
        self.assertEqual(case["register"], [])
        self.assertEqual(case["readyUsed"], 1)
        self.assertEqual(
            case["getRegistration"], [], "no cleanup for the website target"
        )
        self.assertEqual(self._rpc(case, "/mail/push/subscribe")["worker"], "website")
        self.assertEqual(case["storage"], {})

    def test_deferred_subscribes_nothing(self):
        case = self.cases["deferred_target"]
        self.assertEqual(case["result"], {"state": "resolved", "value": True})
        self.assertEqual(case["rpc"], [])
        self.assertEqual(case["register"], [])

    # ------------------------------------------------------------------
    # pushRegistration()
    # ------------------------------------------------------------------

    def test_push_registration_registers_for_backend_and_reads_ready_otherwise(self):
        backend = self.cases["registration_backend"]
        website = self.cases["registration_website"]
        self.assertEqual(backend["result"], "backend")
        self.assertEqual(len(backend["register"]), 1)
        self.assertEqual(backend["readyUsed"], 0)
        self.assertEqual(website["result"], "website")
        self.assertEqual(website["register"], [])
        self.assertEqual(website["readyUsed"], 1)

    # ------------------------------------------------------------------
    # Core's bookkeeping key
    # ------------------------------------------------------------------

    def test_endpoint_storage_key_is_core_s(self):
        """Core's web client compares this key with its subscription to
        detect a lost one; a different spelling would make it re-register."""
        with file_open(CORE_WEBCLIENT) as handle:
            core = handle.read()
        model = re.search(r'const USER_DEVICES_MODEL = "([^"]+)"', core).group(1)
        self.assertIn("`${USER_DEVICES_MODEL}_endpoint`", core)
        core_key = f"{model}_endpoint"
        self.assertEqual(self.cases["constants"]["result"]["coreEndpointKey"], core_key)
        self.assertEqual(
            self.cases["backend_fresh"]["storage"], {core_key: NEW_ENDPOINT}
        )

    # ------------------------------------------------------------------
    # whenActive()
    # ------------------------------------------------------------------

    def test_when_active(self):
        resolved = {"state": "resolved"}
        for name in (
            "active_now",
            "installing_then_activated",
            "waiting_then_activated",
        ):
            self.assertEqual(
                {"state": self.cases[name]["result"]["state"]}, resolved, name
            )
        self.assertEqual(
            self.cases["installing_then_redundant"]["result"],
            {"state": "rejected", "message": "service worker became redundant"},
        )

    def test_when_active_without_any_worker_rejects_instead_of_hanging(self):
        case = self.cases["no_worker"]
        self.assertEqual(case["result"]["state"], "rejected")
        self.assertIn(
            "no installing, waiting or active worker", case["result"]["message"]
        )
        self.assertEqual(len(case["warnings"]), 1)
        self.assertIn("no worker to wait for", case["warnings"][0])

    # ------------------------------------------------------------------
    # PWAPushOpenChannel
    # ------------------------------------------------------------------

    def test_open_channel_message_navigates_to_discuss(self):
        case = self.cases["open_channel"]
        self.assertEqual(case["startMessages"], 1)
        self.assertEqual(
            case["assigned"],
            ["/odoo/action-mail.action_discuss?active_id=discuss.channel_7"],
        )
        self.assertEqual(
            self.cases["open_channel_call"]["assigned"],
            [
                "/odoo/action-mail.action_discuss?active_id=discuss.channel_7&call=accept"
            ],
        )

    def test_other_messages_do_not_navigate(self):
        self.assertEqual(self.cases["open_channel_traversal"]["assigned"], [])
        self.assertEqual(self.cases["other_message"]["assigned"], [])
