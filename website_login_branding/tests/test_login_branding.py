# -*- coding: utf-8 -*-
import re
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, TransactionCase, tagged

CC_LOGO = "/website_login_branding/static/src/img/canarias_conectada_logo.webp"
ZCA_LOGO = "/website_login_branding/static/src/img/zca_logo.webp"


@tagged("post_install", "-at_install")
class TestLoginBranding(HttpCase):
    """Both brand logos and the guest button render on the auth pages."""

    def _assert_branding(self, body):
        self.assertIn(CC_LOGO, body, "Canarias Conectada logo missing")
        self.assertIn(ZCA_LOGO, body, "ZCA logo missing")

    def test_login_page_has_logos(self):
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self._assert_branding(response.text)

    def test_login_page_guest_button_targets_controller(self):
        # The guest button must point at the new controller, never at the old
        # anonymous "/" link.
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self.assertIn("/guest/enter", response.text, "guest button not wired")

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
