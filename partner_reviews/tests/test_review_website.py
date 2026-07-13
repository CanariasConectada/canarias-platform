# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestReviewWebsite(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The default test website belongs to the main company: enable the
        # reviews page there so /resenas resolves on url_open.
        cls.company = cls.env.ref("base.main_company")
        cls.company.enable_reviews = True
        cls.customer = cls.env["res.partner"].create(
            {"name": "PRW Customer", "email": "prw.customer@example.com"}
        )
        cls.env["rating.rating"].create(
            {
                "res_model_id": cls.env["ir.model"]._get_id("res.company"),
                "res_id": cls.company.id,
                "partner_id": cls.customer.id,
                "rating": 4,
                "feedback": "Very nice shop",
                "consumed": True,
            }
        )

    def test_reviews_page_renders(self):
        response = self.url_open("/resenas")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Very nice shop", response.text)
        self.assertIn("PRW Customer", response.text)

    def test_reviews_page_hides_pending(self):
        self.env["review.forbidden.word"].create({"name": "horrible"})
        self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.company"),
                "res_id": self.company.id,
                "partner_id": self.env["res.partner"].create({"name": "PRW Angry"}).id,
                "rating": 1,
                "feedback": "Just horrible, avoid",
                "consumed": True,
            }
        )
        response = self.url_open("/resenas")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Just horrible, avoid", response.text)

    def test_reviews_page_404_when_disabled(self):
        self.company.enable_reviews = False
        response = self.url_open("/resenas")
        self.assertEqual(response.status_code, 404)

    def test_reviews_page_invalid_page_does_not_500(self):
        """A non-numeric ``page`` on the public route must fall back to 1,
        never raise a server error."""
        response = self.url_open("/resenas?page=not-a-number")
        self.assertEqual(response.status_code, 200)
        response = self.url_open("/resenas?page=-5")
        self.assertEqual(response.status_code, 200)

    def test_submit_truncates_long_feedback(self):
        """The public endpoint caps a comment at MAX_FEEDBACK_LENGTH chars."""
        poster = self.env["res.users"].create(
            {
                "name": "PRW Poster",
                "login": "prw_poster",
                "password": "prw_poster_pw",
                "email": "prw.poster@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        self.authenticate("prw_poster", "prw_poster_pw")
        page = self.url_open("/resenas")
        csrf_token = self._extract_csrf_token(page.text)
        response = self.url_open(
            "/resenas/enviar",
            data={
                "rating": "5",
                "feedback": "a" * 3000,
                "csrf_token": csrf_token,
            },
        )
        self.assertEqual(response.status_code, 200)
        review = (
            self.env["rating.rating"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "res.company"),
                    ("res_id", "=", self.company.id),
                    ("partner_id", "=", poster.partner_id.id),
                ]
            )
        )
        self.assertEqual(len(review), 1)
        self.assertEqual(len(review.feedback), 2000)

    def test_submit_review_authenticated(self):
        if not self.env.ref("base.user_demo", raise_if_not_found=False):
            self.skipTest("Requires demo data (demo login)")
        self.authenticate("demo", "demo")
        response = self.url_open("/resenas")
        self.assertEqual(response.status_code, 200)
        csrf_token = self._extract_csrf_token(response.text)
        response = self.url_open(
            "/resenas/enviar",
            data={
                "rating": "5",
                "feedback": "Submitted from the website test",
                "csrf_token": csrf_token,
            },
        )
        self.assertEqual(response.status_code, 200)
        demo_partner = self.env.ref("base.user_demo").partner_id
        review = (
            self.env["rating.rating"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "res.company"),
                    ("res_id", "=", self.company.id),
                    ("partner_id", "=", demo_partner.id),
                ]
            )
        )
        self.assertEqual(len(review), 1)
        self.assertEqual(int(review.rating), 5)
        self.assertEqual(review.moderation_status, "approved")

    @staticmethod
    def _extract_csrf_token(html):
        marker = 'name="csrf_token" value="'
        start = html.index(marker) + len(marker)
        return html[start : html.index('"', start)]
