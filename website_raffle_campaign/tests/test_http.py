# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import re
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user

from .common import TODAY, make_image

HOST = "raffle.test"


@tagged("post_install", "-at_install")
class TestRaffleHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].create(
            {"name": "Raffle http site", "domain": f"http://{HOST}"}
        )
        cls.other_website = cls.env["website"].create(
            {"name": "Raffle other site", "domain": "http://other.raffle.test"}
        )
        cls.merchant = cls.env["res.company"].create({"name": "Http Shop"})
        cls.campaign = cls.env["raffle.campaign"].create(
            {
                "name": "Http raffle",
                "website_id": cls.website.id,
                "slug": "http-raffle",
                "short_path": "/http-short",
                "alias_paths": "/http-typo",
                "date_start": "2026-12-01",
                "date_end": "2026-12-31",
                "min_amount": 15,
                "participating_company_ids": [(6, 0, cls.merchant.ids)],
                "terms_html": "<p>The legal terms text</p>",
                "banner_image": base64.b64encode(make_image(size=(800, 300))),
                "state": "open",
            }
        )
        patcher = patch.object(
            type(cls.env["raffle.campaign"]), "_raffle_today", lambda self: TODAY
        )
        patcher.start()
        cls.addClassCleanup(patcher.stop)

    def _get(self, path, host=HOST, **kwargs):
        return self.url_open(path, headers={"Host": host}, **kwargs)

    def _token(self, html):
        return re.search(r'name="csrf_token" value="([^"]+)"', html).group(1)

    def _post(self, **overrides):
        page = self._get("/sorteo/http-raffle")
        data = {
            "csrf_token": self._token(page.text),
            "participant_name": "Luis Gomez",
            "email": "luis@example.com",
            "phone": "600111222",
            "merchant_id": str(self.merchant.id),
            "amount": "20",
            "purchase_date": "2026-12-05",
            "is_adult": "1",
            "terms_accepted": "1",
        }
        data.update(overrides)
        files = {
            "receipt": (
                "t.png",
                make_image(color=(1, 2, 3)),
                "image/png",
            )
        }
        return self.url_open(
            "/sorteo/http-raffle/submit",
            data=data,
            files=files,
            headers={"Host": HOST},
            allow_redirects=False,
        )

    def test_banner_only_on_homepage_of_right_website_in_window(self):
        home = self._get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("o_raffle_banner", home.text)
        self.assertIn("/sorteo/http-raffle/banner", home.text)
        self.assertIn('href="/http-short"', home.text)
        self.assertNotIn(
            "o_raffle_banner", self._get("/", host="other.raffle.test").text
        )
        self.assertNotIn("o_raffle_banner", self._get("/contactus").text)
        self.campaign.state = "closed"
        self.assertNotIn("o_raffle_banner", self._get("/").text)

    def test_short_path_and_alias(self):
        page = self._get("/http-short")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Registrar mi ticket", page.text)
        alias = self._get("/http-typo", allow_redirects=False)
        self.assertEqual(alias.status_code, 301)
        self.assertTrue(alias.headers["Location"].endswith("/http-short"))
        # The short path belongs to ONE website.
        self.assertEqual(
            self._get("/http-short", host="other.raffle.test").status_code, 404
        )

    def test_pages(self):
        self.assertIn(
            "The legal terms text", self._get("/sorteo/http-raffle/bases").text
        )
        banner = self._get("/sorteo/http-raffle/banner")
        self.assertEqual(banner.status_code, 200)
        self.assertTrue(banner.headers["Content-Type"].startswith("image/"))
        self.assertEqual(self._get("/sorteo/nope").status_code, 404)
        self.campaign.state = "draft"
        # Terms and thank-you stay hidden for a draft; the landing is the
        # "coming soon" page (see test_phases).
        self.assertEqual(self._get("/sorteo/http-raffle/bases").status_code, 404)

    def test_submit_end_to_end_and_receipt_is_private(self):
        response = self._post()
        self.assertIn(response.status_code, (302, 303))
        entry = self.env["raffle.entry"].search(
            [("campaign_id", "=", self.campaign.id)]
        )
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry.email, "luis@example.com")
        thanks = self.url_open(response.headers["Location"], headers={"Host": HOST})
        self.assertIn(entry.reference, thanks.text)
        self.assertIn("o_raffle_ref", thanks.text)
        self.assertIn("Volver a la portada", thanks.text)
        # An anonymous visitor cannot fetch the receipt.
        self.authenticate(None, None)
        att = entry.receipt_attachment_id
        raw = att.raw
        for url in (f"/web/content/{att.id}", f"/web/image/{att.id}"):
            denied = self.url_open(url, headers={"Host": HOST})
            # Odoo answers /web/image with a placeholder rather than an error:
            # what matters is that the receipt bytes never come back.
            self.assertNotEqual(denied.content, raw, url)
            self.assertIn(denied.status_code, (200, 403, 404), url)
        self.assertEqual(
            self.url_open(f"/web/content/{att.id}", headers={"Host": HOST}).status_code,
            404,
        )

    def test_submit_requires_csrf(self):
        response = self.url_open(
            "/sorteo/http-raffle/submit",
            data={"participant_name": "x"},
            headers={"Host": HOST},
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            self.env["raffle.entry"].search([("campaign_id", "=", self.campaign.id)])
        )

    def test_landing_has_every_field_and_the_csrf_token(self):
        html = self._get("/sorteo/http-raffle").text
        self.assertTrue(self._token(html))
        for name in (
            "participant_name",
            "email",
            "phone",
            "merchant_id",
            "amount",
            "purchase_date",
            "receipt",
            "is_adult",
            "terms_accepted",
            "website_url",
        ):
            self.assertIn(f'name="{name}"', html)
        self.assertIn("--raffle-accent: #b3122e", html)
        self.assertIn("Tus datos", html)
        self.assertIn("Tu compra", html)

    def test_accent_reaches_pages_and_banner(self):
        self.campaign.accent_color = "#0a8f5c"
        self.assertIn("--raffle-accent: #0a8f5c", self._get("/sorteo/http-raffle").text)
        self.assertIn("--raffle-accent: #0a8f5c", self._get("/").text)

    def test_server_error_is_a_dismissible_alert(self):
        html = self._post(amount="10").text
        self.assertIn("alert-dismissible", html)
        self.assertIn("La compra debe superar los 15", html)

    def test_form_without_optional_questions(self):
        self.campaign.write({"ask_merchant": False, "ask_amount": False})
        html = self._get("/sorteo/http-raffle").text
        self.assertNotIn('name="merchant_id"', html)
        self.assertNotIn('name="amount"', html)
        self.assertIn('name="purchase_date"', html)
        # min_amount stays visible as a participation rule.
        self.assertIn("de más de 15", html)
        response = self._post(merchant_id="", amount="")
        self.assertIn(response.status_code, (302, 303))
        entry = self.env["raffle.entry"].search(
            [("campaign_id", "=", self.campaign.id)]
        )
        self.assertEqual(len(entry), 1)
        self.assertFalse(entry.merchant_id)

    def test_pages_without_artwork_get_a_typographic_hero(self):
        self.campaign.banner_image = False
        for path in ("/sorteo/http-raffle", "/sorteo/http-raffle/gracias"):
            html = self._get(path).text
            self.assertIn("o_raffle_hero_title", html, path)
            self.assertNotIn("o_raffle_art", html, path)
        self.assertEqual(self._get("/sorteo/http-raffle/banner").status_code, 404)
        home = self._get("/").text
        self.assertIn("o_raffle_banner_slim", home)
        self.assertIn("Http raffle", home)
        self.campaign.state = "closed"
        self.assertNotIn("o_raffle_banner", self._get("/").text)

    def test_validation_error_rerenders_with_values(self):
        response = self._post(amount="10", participant_name="Keep Me")
        self.assertEqual(response.status_code, 200)
        self.assertIn("La compra debe superar los 15", response.text)
        self.assertIn("Keep Me", response.text)
        self.assertFalse(
            self.env["raffle.entry"].search([("campaign_id", "=", self.campaign.id)])
        )

    def test_lang_prefix_on_short_path_and_alias(self):
        lang = self.env["res.lang"]._activate_lang("fr_FR")
        self.website.language_ids = [(4, lang.id)]
        page = self._get("/fr/http-short")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Registrar mi ticket", page.text)
        alias = self._get("/fr/http-typo", allow_redirects=False)
        self.assertEqual(alias.status_code, 301)
        self.assertTrue(
            alias.headers["Location"].endswith("/fr/http-short"),
            alias.headers["Location"],
        )

    def test_oversized_body_refused_by_route(self):
        page = self._get("/sorteo/http-raffle")
        response = self.url_open(
            "/sorteo/http-raffle/submit",
            data={"csrf_token": self._token(page.text)},
            files={
                "receipt": (
                    "big.pdf",
                    b"%PDF-" + b"0" * (12 * 1024 * 1024),
                    "application/pdf",
                )
            },
            headers={"Host": HOST},
        )
        self.assertEqual(response.status_code, 413)
        self.assertFalse(
            self.env["raffle.entry"].search([("campaign_id", "=", self.campaign.id)])
        )

    def test_submit_ip_is_audit_only(self):
        self._post()
        entry = self.env["raffle.entry"].search(
            [("campaign_id", "=", self.campaign.id)]
        )
        self.assertTrue(entry.submit_ip)

    # -- phases -----------------------------------------------------------
    def _assert_styled_404(self, response):
        self.assertEqual(response.status_code, 404)
        self.assertIn('id="wrapwrap"', response.text)  # the site layout
        self.assertNotIn("The requested URL was not found on the server", response.text)

    def _assert_soon(self, response):
        self.assertEqual(response.status_code, 200)
        self.assertIn("Muy pronto", response.text)
        self.assertIn('id="wrapwrap"', response.text)
        self.assertNotIn("<form", response.text.split('id="wrap"')[1])
        self.assertNotIn("/bases", response.text)

    def test_phases(self):
        for path in ("/http-short", "/sorteo/http-raffle"):
            with self.subTest("draft " + path):
                self.campaign.state = "draft"
                self._assert_soon(self._get(path))
            with self.subTest("open before start " + path):
                self.campaign.write({"state": "open", "date_start": "2026-12-20"})
                response = self._get(path)
                self._assert_soon(response)
                self.assertRegex(
                    response.text, "20 de diciembre de 2026|December 20, 2026"
                )
                self.campaign.write({"date_start": "2026-12-01"})
            with self.subTest("inside window " + path):
                response = self._get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Registrar mi ticket", response.text)
            with self.subTest("after end " + path):
                self.campaign.write({"date_end": "2026-12-05"})
                response = self._get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("ha finalizado", response.text)
                self.assertNotIn("Registrar mi ticket", response.text)
                self.campaign.write({"date_end": "2026-12-31"})
            with self.subTest("closed " + path):
                self.campaign.state = "closed"
                self.assertIn("ha finalizado", self._get(path).text)
                self.campaign.state = "open"

    def test_ended_shows_draw_date_until_drawn(self):
        self.campaign.write({"state": "closed", "draw_date": "2027-01-02"})
        text = self._get("/http-short").text
        self.assertRegex(text, "2 de enero de 2027|January 2, 2027")
        self.campaign.state = "drawn"
        self.assertNotRegex(
            self._get("/http-short").text, "2 de enero de 2027|January 2, 2027"
        )

    def test_submit_still_rejected_outside_the_window(self):
        for vals in ({"state": "draft"}, {"state": "open", "date_start": "2026-12-20"}):
            self.campaign.write(vals)
            with self.assertRaises(UserError):
                self.campaign._submit_entry({}, None, "1.1.1.1")
            self.campaign.write({"state": "open", "date_start": "2026-12-01"})

    def test_unknown_paths_get_the_styled_404(self):
        self._assert_styled_404(self._get("/no-such-campaign"))
        self._assert_styled_404(self._get("/sorteo/nope"))
        self._assert_styled_404(self._get("/sorteo/http-raffle/bases/extra"))
        self.campaign.active = False
        self._assert_styled_404(self._get("/http-short"))
        self._assert_styled_404(self._get("/sorteo/http-raffle"))

    def test_lang_prefix_on_coming_soon(self):
        lang = self.env["res.lang"]._activate_lang("fr_FR")
        self.website.language_ids = [(4, lang.id)]
        self.campaign.state = "draft"
        self._assert_soon(self._get("/fr/http-short"))
        self._assert_soon(self._get("/fr/sorteo/http-raffle"))

    def test_admin_sees_preview_notice_on_draft(self):
        self.campaign.state = "draft"
        self.assertNotIn("Vista previa", self._get("/http-short").text)
        new_test_user(self.env, "raffle_http_admin", groups="base.group_system")
        self.authenticate("raffle_http_admin", "raffle_http_admin")
        # A custom Host header drops the test session cookie, so make this
        # site the default one instead and call without it.
        self.website.sequence = -1000
        for path in ("/http-short", "/sorteo/http-raffle"):
            text = self.url_open(path).text
            self.assertIn("Vista previa: la campaña está en borrador", text)
            self.assertNotIn("Muy pronto", text)

    def test_coming_soon_not_stuck_after_opening(self):
        self.campaign.state = "draft"
        self._assert_soon(self._get("/http-short"))
        self.campaign.state = "open"
        self.assertIn("Registrar mi ticket", self._get("/http-short").text)
        self.assertNotIn("Muy pronto", self._get("/sorteo/http-raffle").text)

    def test_status_pages_are_not_cacheable(self):
        self.campaign.state = "draft"
        response = self._get("/http-short")
        self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
