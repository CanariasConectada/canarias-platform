# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
import time

from odoo.tests import HttpCase, tagged

from odoo.addons.discuss_community.controllers.main import (
    COMMUNITY_GUEST_WINDOW_COUNT_PARAM,
    COMMUNITY_GUEST_WINDOW_MAX,
    COMMUNITY_GUEST_WINDOW_START_PARAM,
)

from .common import CommunityMixin


@tagged("post_install", "-at_install")
class TestCommunityRoutes(CommunityMixin, HttpCase):
    """/community routes by identity; /community/guest mints with guards."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_community_fixtures()
        cls.portal_user = (
            cls.env["res.users"]
            .with_context(no_reset_password=True)
            .create(
                {
                    "name": "DCM Portal",
                    "login": "dcm_portal",
                    "password": "dcm_portal",
                    "email": "dcm_portal@example.com",
                    "company_id": cls.main_company.id,
                    "company_ids": [(6, 0, cls.main_company.ids)],
                    "group_ids": [(6, 0, cls.portal_group.ids)],
                }
            )
        )

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _guest_count(self):
        return (
            self.env["res.users"]
            .sudo()
            .search_count([("is_community_guest", "=", True)])
        )

    def _enter(self, redirect=None):
        """POST /community/guest the way the landing page's form does.

        The route is POST-only and CSRF-protected; the token is scraped from
        the form the /community page renders, which also primes the session
        cookie the POST rides on -- same technique as the /guest/enter suite.
        """
        page = self.url_open("/community")
        match = re.search(r'csrf_token"[^>]*value="([^"]+)"', page.text)
        self.assertTrue(match, "/community carries no csrf token")
        data = {"csrf_token": match.group(1)}
        if redirect is not None:
            data["redirect"] = redirect
        return self.url_open("/community/guest", data=data, timeout=30)

    # ------------------------------------------------------------------
    # /community
    # ------------------------------------------------------------------

    def test_anonymous_landing_offers_exactly_the_two_doors(self):
        """The public page holds the guest POST form and the signup link.

        The guest entry must be a FORM (a mutating route can never be a
        link), and both targets are asserted so a template edit cannot
        silently unwire a door.
        """
        response = self.url_open("/community")
        self.assertEqual(response.status_code, 200)
        self.assertIn('action="/community/guest"', response.text)
        self.assertIn('method="post"', response.text)
        self.assertIn('href="/web/signup"', response.text)

    def test_logged_internal_user_is_sent_to_the_backend(self):
        """An internal session on /community belongs in Discuss, i.e. /odoo."""
        self.authenticate("dcm_member", "dcm_member")
        response = self.url_open("/community", allow_redirects=False)
        self.assertIn(response.status_code, (301, 302, 303, 307))
        self.assertTrue(
            response.headers.get("Location", "").endswith("/odoo"),
            "internal users must be redirected to the backend",
        )

    def test_logged_portal_user_gets_the_card_with_a_note(self):
        """A portal session is not community: it gets the card, not /chat.

        Phase 1 routed these sessions to the legacy /chat pages; Phase 3
        retires those pages behind a 301 back to /community
        (``website_pwa_chat_community_redirect``), so a redirect to /chat
        here would loop. The branch must RENDER: the card with a note and a
        log-out door, and neither of the two anonymous doors -- both would
        be dead buttons under an authenticated session (/community/guest
        refuses to mint or swap, /web/signup fights the login).
        """
        self.authenticate("dcm_portal", "dcm_portal")
        response = self.url_open("/community", allow_redirects=False)
        self.assertEqual(
            response.status_code,
            200,
            "the portal branch must render, never redirect: /chat 301s back "
            "here once the Phase 3 bridge is installed",
        )
        self.assertIn("o_cc_portal_note", response.text)
        self.assertIn("/web/session/logout?redirect=/community", response.text)
        self.assertNotIn(
            'action="/community/guest"',
            response.text,
            "the guest door is a dead button under an authenticated session",
        )
        self.assertNotIn(
            'href="/web/signup"',
            response.text,
            "so is signup; only the log-out door may be offered",
        )

    def test_community_never_redirects_anybody_to_chat(self):
        """The /community half of the no-loop contract, per persona.

        Phase 3's bridge makes /chat answer 301 /community, so ANY answer
        from this route pointing at /chat is a loop waiting for the bridge.
        Asserted for the three session shapes the route distinguishes:
        anonymous and portal must render (200), internal must leave for
        /odoo -- never for /chat.
        """
        personas = (
            ("anonymous", None),
            ("portal", "dcm_portal"),
            ("internal member", "dcm_member"),
        )
        for label, login in personas:
            with self.subTest(persona=label):
                self.authenticate(login, login)
                response = self.url_open("/community", allow_redirects=False)
                location = response.headers.get("Location", "")
                self.assertFalse(
                    location.rstrip("/").endswith("/chat"),
                    "/community sent the %s persona to /chat: that is a "
                    "redirect loop once the Phase 3 bridge is installed" % label,
                )
                if login == "dcm_member":
                    self.assertTrue(location.endswith("/odoo"))
                else:
                    self.assertEqual(response.status_code, 200)

    # ------------------------------------------------------------------
    # /community/guest
    # ------------------------------------------------------------------

    def test_guest_enter_creates_an_internal_guest_then_reuses_it(self):
        """First click mints one guest; the signed cookie makes clicks after
        that idempotent.

        The session cookie is dropped between the two hits ON PURPOSE while
        the ``cc_community_guest`` cookie is kept: that forces the second hit
        down the HMAC-validated reuse path instead of the "already logged in"
        shortcut. Reuse, not duplication, is the whole point of the cookie.
        """
        before = self._guest_count()
        self._enter()
        self.assertEqual(self._guest_count(), before + 1, "guest not created")
        guest = (
            self.env["res.users"]
            .sudo()
            .search([("is_community_guest", "=", True)], order="id desc", limit=1)
        )
        self.assertTrue(guest._is_internal())
        self.opener.cookies.pop("session_id", None)
        self._enter()
        self.assertEqual(self._guest_count(), before + 1, "guest was duplicated")

    def test_guest_enter_rejects_offsite_redirect(self):
        """`redirect` is attacker-reachable; only same-site paths survive."""
        response = self._enter(redirect="http://evil.example/pwn")
        self.assertNotIn("evil.example", response.url, "open redirect not blocked")

    def test_guest_enter_refuses_get(self):
        """A plain GET must bounce (405): prefetchers and link scanners must
        not be able to mint internal accounts."""
        response = self.url_open("/community/guest")
        self.assertEqual(response.status_code, 405)

    def test_guest_enter_respects_the_rolling_window_cap(self):
        """With the window already full, the click degrades, mints nothing.

        The cap is the only brake on a bot flooding BRAND-NEW sessions (real
        visitors ride the reuse cookie); the degraded answer must still be a
        redirect, never a 500 in the visitor's face.
        """
        icp = self.env["ir.config_parameter"].sudo()
        icp.set_param(COMMUNITY_GUEST_WINDOW_START_PARAM, str(int(time.time())))
        icp.set_param(
            COMMUNITY_GUEST_WINDOW_COUNT_PARAM, str(COMMUNITY_GUEST_WINDOW_MAX)
        )
        try:
            before = self._guest_count()
            response = self._enter()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                self._guest_count(), before, "the cap must refuse creation"
            )
        finally:
            icp.set_param(COMMUNITY_GUEST_WINDOW_COUNT_PARAM, "0")
