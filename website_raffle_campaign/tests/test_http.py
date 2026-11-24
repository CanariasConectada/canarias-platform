# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import re
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

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
        self.assertEqual(self._get("/sorteo/http-raffle").status_code, 404)

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
