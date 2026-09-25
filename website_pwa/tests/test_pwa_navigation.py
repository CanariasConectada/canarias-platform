# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import re

from odoo.tests import HttpCase, tagged
from odoo.tools import file_open

from odoo.addons.website_pwa.controllers.main import SERVICE_WORKER_PATH

HOME_SYSTRAY_JS = "website_pwa/static/src/backend/home_systray.js"
HOME_SYSTRAY_XML = "website_pwa/static/src/backend/home_systray.xml"
BACKEND_SCOPE = "/odoo"


def _make_user(env, login, group_xmlid):
    """A user whose password the test knows: the lab database is a copy of
    production, where "admin" does not log in with "admin"."""
    return (
        env["res.users"]
        .with_context(no_reset_password=True)
        .create(
            {
                "name": login,
                "login": login,
                "password": login,
                "group_ids": [(6, 0, [env.ref(group_xmlid).id])],
            }
        )
    )


def _in_scope(path, scope):
    """The Web App Manifest rule: a URL is within scope when its path starts
    with the scope's path."""
    return path.startswith(scope)


@tagged("post_install", "-at_install")
class TestPWAConsistency(HttpCase):
    """The installed app, its worker and the backend's worker must agree.

    One origin serves two apps' worth of plumbing: the website app
    (website_pwa, scope "/") and core's backend app (scope "/odoo"). Push and
    navigation only work when the pieces line up, so the lining up is tested
    here rather than assumed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.pwa_enabled = True
        cls.internal_user = _make_user(cls.env, "pwa_nav_internal", "base.group_user")

    def _manifest(self):
        res = self.url_open("/website_pwa/manifest.webmanifest")
        self.assertEqual(res.status_code, 200)
        return json.loads(res.text)

    def test_start_url_is_inside_the_scope(self):
        manifest = self._manifest()
        self.assertTrue(_in_scope(manifest["start_url"], manifest["scope"]))

    def test_worker_is_allowed_the_whole_manifest_scope(self):
        """The worker must be able to control everything the app shows."""
        manifest = self._manifest()
        res = self.url_open(SERVICE_WORKER_PATH)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Service-Worker-Allowed"), manifest["scope"])

    def test_page_script_registers_the_served_worker_with_the_manifest_scope(self):
        """The registration in pwa_install.js, the route and the manifest
        name the same file and the same scope. A drift between the three is
        a worker that installs but controls nothing the app opens."""
        manifest = self._manifest()
        with file_open("website_pwa/static/src/js/pwa_install.js") as f:
            script = f.read()
        match = re.search(
            r'serviceWorker\.register\("([^"]+)",\s*\{scope:\s*"([^"]+)"\}\)', script
        )
        self.assertTrue(match, "the page script no longer registers the worker")
        self.assertEqual(match.group(1), SERVICE_WORKER_PATH)
        self.assertEqual(match.group(2), manifest["scope"])

    def test_the_backend_stays_inside_the_installed_app(self):
        """Signing in from the installed app lands in /odoo. That has to be
        inside the app's scope or the backend opens in a browser sheet, with
        its own cookie jar on iOS -- and the push subscription made there
        would belong to a different app than the one on the home screen."""
        manifest = self._manifest()
        self.assertTrue(_in_scope(BACKEND_SCOPE, manifest["scope"]))
        self.assertFalse(
            _in_scope(manifest["start_url"], BACKEND_SCOPE),
            "the app must open on the website, not on the backend worker's pages",
        )

    def test_core_backend_worker_keeps_its_own_narrower_scope(self):
        """Core's worker is the one carrying the Discuss push handler for
        internal users. Its scope must stay /odoo, nested inside the website
        app, never "/" competing with the website worker for the same pages."""
        res = self.url_open("/web/service-worker.js")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Service-Worker-Allowed"), BACKEND_SCOPE)
        backend_manifest = json.loads(self.url_open("/web/manifest.webmanifest").text)
        self.assertEqual(backend_manifest["scope"], BACKEND_SCOPE)

    def test_internal_users_get_the_push_handler_in_the_backend_worker(self):
        """Core only appends mail's push handler for an internal user. This is
        why internal users are subscribed on the backend worker and not on the
        website one, which has no handler unless push is on for the site."""
        self.authenticate("pwa_nav_internal", "pwa_nav_internal")
        body = self.url_open("/web/service-worker.js").text
        self.assertIn('addEventListener("push"', body)
        self.assertIn('addEventListener("notificationclick"', body)


@tagged("post_install", "-at_install")
class TestQuickAccessBlock(HttpCase):
    def test_block_carries_the_classes_the_install_script_drives(self):
        """Reusing pwa_install.js only works if the block speaks its classes;
        the install button and the iOS steps both start hidden."""
        html = str(
            self.env["ir.qweb"]._render(
                "website_pwa.pwa_install_quick_access",
                {"website": self.env.ref("website.default_website")},
            )
        )
        self.assertIn("o_pwa_install_card", html)
        self.assertIn("o_pwa_quick_access", html)
        self.assertRegex(html, r'class="[^"]*o_pwa_install_button[^"]*d-none')
        self.assertRegex(html, r'class="[^"]*o_pwa_ios_hint[^"]*d-none')
        self.assertIn("Add to Home Screen", html)


@tagged("post_install", "-at_install")
class TestBackendHomeEntry(HttpCase):
    def _asset_paths(self, bundle):
        ir_asset = self.env["ir.asset"]
        return [
            asset[0]
            for asset in ir_asset._get_asset_paths(bundle, ir_asset._get_asset_params())
        ]

    def test_home_entry_is_in_the_backend_bundle(self):
        backend = self._asset_paths("web.assets_backend")
        for path in (HOME_SYSTRAY_JS, HOME_SYSTRAY_XML):
            self.assertTrue(
                any(asset.endswith(path) for asset in backend),
                f"{path} is not in web.assets_backend",
            )

    def test_home_entry_is_not_shipped_to_the_website(self):
        frontend = self._asset_paths("web.assets_frontend")
        self.assertFalse(any(asset.endswith(HOME_SYSTRAY_JS) for asset in frontend))

    def _assert_home_entry(self, login):
        code = """
            const link = document.querySelector(".o_cc_home_systray a");
            if (link && link.getAttribute("href") === "/") {
                console.log("test successful");
            } else {
                console.error("Canarias Conectada home entry missing or wrong");
            }
        """
        self.browser_js(
            "/odoo/discuss",
            code,
            ready="!!document.querySelector('.o_cc_home_systray')",
            login=login,
        )

    def test_administrator_sees_the_home_entry_in_discuss(self):
        _make_user(self.env, "pwa_nav_admin", "base.group_system")
        self._assert_home_entry("pwa_nav_admin")

    def test_plain_internal_user_sees_the_home_entry(self):
        """Not a website-editor feature: every internal user needs the way
        back, merchants and community guests included."""
        _make_user(self.env, "pwa_nav_employee", "base.group_user")
        self._assert_home_entry("pwa_nav_employee")
