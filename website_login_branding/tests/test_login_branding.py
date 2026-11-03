# -*- coding: utf-8 -*-
import re
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged
from odoo.tests import common as test_common
from odoo.tests.common import ChromeBrowser

CC_LOGO = "/website_login_branding/static/src/img/canarias_conectada_logo.webp"
FUNDING_STRIP = "/website_login_branding/static/src/img/subvenciones.png"


@tagged("post_install", "-at_install")
class TestLoginBranding(HttpCase):
    """Both brand logos and the guest button render on the auth pages."""

    def _assert_branding(self, body):
        self.assertIn(CC_LOGO, body, "Canarias Conectada logo missing")
        self.assertIn(FUNDING_STRIP, body, "funding strip missing")
        self.assertIn("o_cc_login_subvention_logo", body, "funding strip class missing")
        self.assertIn("FEDER Canarias 2021-2027", body, "FEDER legend missing")
        self.assertIn("NextGenerationEU", body, "NextGenerationEU legend missing")

    def test_login_page_has_logos(self):
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self._assert_branding(response.text)

    def test_login_page_guest_button_targets_controller(self):
        # The guest button must point at a mutating POST controller, never at
        # the old anonymous "/" link. NOT asserted on the specific "/guest/
        # enter" URL: `discuss_community`, when installed, overrides this
        # very form to post to its own "/community/guest" instead (see
        # discuss_community.login_guest_uses_community_door) so that a guest
        # from /login gets the same account as one from /community. This
        # module must not know that override exists or start failing when it
        # runs -- the button's PRESENCE and shape are its contract, not which
        # controller answers it.
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_cc_guest_btn", response.text, "guest button not wired")
        self.assertIn(
            'method="post"',
            response.text,
            "guest button must submit through POST, never a plain link",
        )

    def test_signup_page_has_logos(self):
        # Public signup can be disabled per database, in which case the
        # route answers 404 and there is no page to check.
        response = self.url_open("/web/signup")
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 200:
            self.assertIn("oe_website_login_container", response.text)
            self._assert_branding(response.text)

    def test_reset_password_page_has_logos(self):
        response = self.url_open("/web/reset_password")
        self.assertEqual(response.status_code, 200)
        self.assertIn("oe_website_login_container", response.text)
        self._assert_branding(response.text)


@tagged("post_install", "-at_install")
class TestGuestEnter(HttpCase):
    """The /guest/enter controller creates, reuses and never over-trusts."""

    def _guest_count(self):
        return (
            self.env["res.users"]
            .sudo()
            .search_count([("is_platform_guest", "=", True)])
        )

    def _enter(self, redirect=None):
        """POST /guest/enter the way the login page's form does.

        The route is POST-only (it mutates: creates/logs in a user), so it
        demands a csrf token; grab the one the login page renders inside the
        guest form. The token is bound to the current session, so this fetch
        also primes the session cookie the POST rides on.
        """
        page = self.url_open("/web/login")
        match = re.search(r'csrf_token"[^>]*value="([^"]+)"', page.text)
        self.assertTrue(match, "login page carries no csrf token")
        data = {"csrf_token": match.group(1)}
        if redirect is not None:
            data["redirect"] = redirect
        return self.url_open("/guest/enter", data=data, timeout=30)

    def test_guest_enter_creates_then_reuses(self):
        before = self._guest_count()
        # First hit creates exactly one guest...
        self._enter()
        self.assertEqual(self._guest_count(), before + 1, "guest not created")
        # ...drop the session cookie but KEEP the signed cc_guest cookie so the
        # next hit is forced down the cookie-reuse path (the HMAC round-trip)
        # instead of the "already logged in" shortcut. It must reuse, not
        # duplicate.
        self.opener.cookies.pop("session_id", None)
        self._enter()
        self.assertEqual(self._guest_count(), before + 1, "guest was duplicated")

    def test_guest_enter_rejects_offsite_redirect(self):
        response = self._enter(redirect="http://evil.example/pwn")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("evil.example", response.url, "open redirect was not blocked")

    def test_guest_enter_refuses_get(self):
        """The route mutates state; a plain GET must bounce off (405), which
        is what keeps prefetchers and link scanners from minting guests."""
        response = self.url_open("/guest/enter")
        self.assertEqual(response.status_code, 405)


@tagged("post_install", "-at_install")
class TestGuestModel(TransactionCase):
    """Unit coverage for the guest lifecycle helpers."""

    def test_create_platform_guest_shape(self):
        guest = self.env["res.users"]._create_platform_guest()
        self.assertTrue(guest.is_platform_guest)
        self.assertTrue(guest.share, "guest must be a share/portal user")
        portal = self.env.ref("base.group_portal")
        internal = self.env.ref("base.group_user")
        self.assertIn(portal, guest.all_group_ids)
        self.assertNotIn(internal, guest.all_group_ids, "guest got internal group")
        self.assertTrue(guest.login.endswith("@guests.canariasconectada.es"))

    def test_gc_removes_idle_empty_guest(self):
        guest = self.env["res.users"]._create_platform_guest()
        # Backdate creation past the staleness window; the account has no login
        # log, so it is idle by definition.
        old = fields.Datetime.now() - timedelta(days=30)
        self.env.cr.execute(
            "UPDATE res_users SET create_date = %s WHERE id = %s",
            (old, guest.id),
        )
        guest.invalidate_recordset(["create_date"])

        removed = self.env["res.users"]._gc_platform_guests()
        self.assertGreaterEqual(removed, 1)
        self.assertFalse(guest.exists(), "stale guest was not purged")

    # ------------------------------------------------------------------
    # Undeliverable mail
    # ------------------------------------------------------------------

    def test_rotating_a_guest_password_queues_no_mail(self):
        """The guest domain is non-routable, so the warning can only bounce.

        `/guest/enter` rotates the password on every visit, so without this
        every anonymous arrival queued a "Security Update: Password Changed"
        addressed to a domain with no MX -- charged against the sender
        reputation of every real email the platform sends.
        """
        guest = self.env["res.users"]._create_platform_guest()
        before = self.env["mail.mail"].sudo().search_count([])

        guest.sudo().write({"password": "rotado-por-el-test"})

        self.assertEqual(
            self.env["mail.mail"].sudo().search_count([]),
            before,
            "a guest password rotation must not queue mail",
        )

    def test_a_real_user_is_still_warned(self):
        """Only guests are silenced. Everybody else keeps core's warning."""
        user = self.env["res.users"].create(
            {
                "name": "Cliente de verdad",
                "login": "cliente_de_verdad",
                "email": "cliente@example.com",
            }
        )
        before = self.env["mail.mail"].sudo().search_count([])

        user.write({"password": "una-contrasena-nueva"})

        self.assertGreater(
            self.env["mail.mail"].sudo().search_count([]),
            before,
            "a real account must still be told its password changed",
        )


@tagged("post_install", "-at_install")
class TestLoginPwaQuickAccess(HttpCase):
    """ "Download Canarias Conectada" on the auth pages."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env.ref("website.default_website")
        cls.website.pwa_enabled = True

    def _assert_block(self, body):
        self.assertIn("o_cc_login_pwa", body)
        # The install card is website_pwa's own, driven by its script.
        self.assertIn("o_pwa_install_card", body)
        self.assertIn("o_pwa_install_button", body)
        self.assertIn("o_pwa_ios_hint", body)
        # The notification card, only inside the installed app, and marked
        # as a login-page card so an anonymous visitor's grant is deferred.
        self.assertIn("o_pwa_push_card", body)
        self.assertIn('data-pwa-push-context="login"', body)
        self.assertIn('data-pwa-push-standalone="1"', body)
        # The scripts that drive both cards travel in the frontend bundle the
        # page loads; the card is inert without them.
        self.assertIn('rel="manifest"', body)

    def test_login_page_offers_the_app(self):
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self._assert_block(response.text)

    def test_reset_password_page_offers_the_app(self):
        response = self.url_open("/web/reset_password")
        self.assertEqual(response.status_code, 200)
        self._assert_block(response.text)

    def test_signup_page_offers_the_app(self):
        response = self.url_open("/web/signup")
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 200:
            self._assert_block(response.text)

    def test_block_sits_below_the_guest_entry(self):
        body = self.url_open("/web/login").text
        self.assertLess(body.index("o_cc_login_guest"), body.index("o_cc_login_pwa"))

    def test_no_block_when_the_app_is_disabled(self):
        """Without a manifest there is nothing to install: the block would
        be a promise the browser refuses."""
        self.website.pwa_enabled = False
        self.assertNotIn("o_cc_login_pwa", self.url_open("/web/login").text)

    def test_block_is_translated_to_spanish(self):
        lang = self.env["res.lang"]._activate_lang("es_ES")
        self.env["ir.module.module"]._load_module_terms(
            ["website_pwa", "website_pwa_push"], ["es_ES"], overwrite=True
        )
        self.website.language_ids |= lang
        self.website.default_lang_id = lang
        # The visitor's language cookie outranks the website default.
        self.opener.cookies.set("frontend_lang", "es_ES")
        body = self.url_open("/web/login").text
        self.assertIn("Descarga Canarias Conectada", body)
        self.assertIn("Activar notificaciones", body)


# Injected before any page script runs, on every document of the browser run.
# Only the login page loses the APIs: the backend it lands on afterwards is
# core's web client, whose own tolerance is not what is under test here.
_BREAK_PUSH_APIS = """
(() => {
    // `includes`, not `startsWith`: the page may be served under a language
    // prefix (/en/web/login).
    if (!location.pathname.includes("/web/login")) {
        if (location.pathname.startsWith("/odoo")) {
            document.addEventListener("DOMContentLoaded", () => {
                console.log("test successful");
            });
        }
        return;
    }
    const mode = %(mode)s;
    const names = ["Notification", "PushManager"];
    if (mode === "delete") {
        for (const name of names) {
            delete window[name];
        }
        delete Navigator.prototype.serviceWorker;
    } else {
        const boom = (name) => ({
            configurable: true,
            get() {
                throw new Error(name + " is blocked in this browser");
            },
        });
        // Only `PushManager` throws. A throwing `Notification` or
        // `navigator.serviceWorker` breaks CORE's frontend on every page,
        // before or beside any of our code: `@web/core/browser/browser`
        // reads `window.Notification` at module definition and mail's
        // `store_service` reads `navigator.serviceWorker?.` at start (the
        // `?.` still runs the getter). Those two are removed instead; the
        // page scripts' own try/catch around them is exercised by the node
        // harness, not here.
        delete window.Notification;
        delete Navigator.prototype.serviceWorker;
        Object.defineProperty(window, "PushManager", boom("PushManager"));
    }
})();
"""

# Runs once the login page is ready: give the public interactions time to
# start (they are what touches the APIs), then submit the real form.
_SUBMIT_LOGIN = """
let broken;
try {
    broken = !navigator.serviceWorker && !window.Notification && !window.PushManager;
} catch {
    broken = true;
}
if (!broken) {
    console.error("the push APIs were not broken on the login page");
}
setTimeout(() => {
    const form = document.querySelector("form.oe_login_form");
    form.querySelector("input[name=login]").value = "cc_resilience";
    form.querySelector("input[name=password]").value = "cc_resilience_pwd";
    form.querySelector("button[type=submit]").click();
}, 1500);
"""


@tagged("post_install", "-at_install")
class TestLoginWithoutPushApis(HttpCase):
    """The app plumbing on the login page must never cost a login.

    Privacy modes, in-app browsers and old engines either lack the Push API
    entirely or expose accessors that throw when read. Any uncaught error
    fails the test (the browser harness turns it into a failure), and the
    only success signal is emitted by the backend page reached AFTER the form
    was submitted.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.ref("website.default_website").pwa_enabled = True
        cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "Resilience",
                "login": "cc_resilience",
                "password": "cc_resilience_pwd",
                "group_ids": [(6, 0, [cls.env.ref("base.group_user").id])],
            }
        )

    def setUp(self):
        super().setUp()
        # No screencast: the page keeps repainting up to the moment the
        # harness closes Chrome, and with screencasts on (CI and the lab) a
        # frame acknowledged on the closing socket fails the test with a
        # BrokenPipeError AFTER the browser check has already succeeded.
        self.startPatcher(
            patch.object(
                test_common, "Screencaster", lambda *args: test_common.NoScreencast()
            )
        )

    def _login_with_apis(self, mode):
        original = ChromeBrowser.navigate_to
        source = _BREAK_PUSH_APIS % {"mode": '"%s"' % mode}

        def navigate_to(browser, url, wait_stop=False):
            browser._websocket_request(
                "Page.addScriptToEvaluateOnNewDocument", params={"source": source}
            )
            return original(browser, url, wait_stop=wait_stop)

        with patch.object(ChromeBrowser, "navigate_to", navigate_to):
            self.browser_js(
                "/web/login",
                _SUBMIT_LOGIN,
                ready="!!document.querySelector('.o_cc_login_pwa')",
            )

    def test_login_works_when_the_apis_are_missing(self):
        self._login_with_apis("delete")

    def test_login_works_when_push_manager_throws(self):
        self._login_with_apis("throw")
