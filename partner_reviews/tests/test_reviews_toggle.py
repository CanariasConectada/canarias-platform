# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

from ..models.res_company import REVIEWS_PAGE_URL


@tagged("post_install", "-at_install")
class TestReviewsToggleInEditor(HttpCase):
    """A merchant switching their own reviews page on and off.

    Client request 2026-09-16: the switch lived on the company form alone,
    which no merchant can save. It now sits on the merchant's content editor,
    goes through the editor's ownership check, and the company form's
    Microsite page shows the same switch.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # no_microsite_auto: auto_microsite_generator (co-installed in the
        # full image) must not provision a second website per company.
        cls.env = cls.env(
            context=dict(
                cls.env.context,
                no_reset_password=True,
                no_microsite_auto=True,
                tracking_disable=True,
            )
        )
        cls.shop = cls.env["res.company"].create({"name": "PRT Bakery"})
        cls.shop.website_id = cls.env["website"].create(
            {"name": "PRT Bakery", "company_id": cls.shop.id}
        )
        cls.stranger = cls.env["res.company"].create({"name": "PRT Stranger"})
        cls.stranger.website_id = cls.env["website"].create(
            {"name": "PRT Stranger", "company_id": cls.stranger.id}
        )
        cls.merchant = new_test_user(
            cls.env,
            login="prt_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
        )

    def _editor(self):
        return self.env["microsite.content.editor"].with_user(self.merchant)

    def _reviews_menus(self, company):
        return self.env["website.menu"].search(
            [("website_id", "=", company.website_id.id), ("url", "=", REVIEWS_PAGE_URL)]
        )

    def _toggle(self, value):
        editor = self._editor().create({"enable_reviews": value})
        editor.action_save()

    def _open_reviews_page(self):
        # Serve the shop's own website on the test server's address.
        self.shop.website_id.domain = self.base_url()
        return self.url_open(REVIEWS_PAGE_URL, allow_redirects=True)

    def test_merchant_enables_the_reviews_page(self):
        self.assertFalse(self.shop.enable_reviews)
        self._toggle(True)
        self.assertTrue(self.shop.enable_reviews)
        self.assertEqual(len(self._reviews_menus(self.shop)), 1)
        response = self._open_reviews_page()
        self.assertEqual(response.status_code, 200)
        # The shop's own page, not the platform's (which may accept reviews).
        self.assertIn("PRT Bakery", response.text)

    def test_saving_again_does_not_duplicate_the_menu_entry(self):
        self._toggle(True)
        self._toggle(True)
        self.assertEqual(len(self._reviews_menus(self.shop)), 1)

    def test_merchant_disables_the_reviews_page(self):
        self._toggle(True)
        self._toggle(False)
        self.assertFalse(self.shop.enable_reviews)
        self.assertFalse(self._reviews_menus(self.shop))
        response = self._open_reviews_page()
        self.assertIn(response.status_code, (404, 301, 302, 303))

    def test_the_editor_opens_with_the_shop_value_and_figures(self):
        self.shop.enable_reviews = True
        self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.company"),
                "res_id": self.shop.id,
                "partner_id": self.env["res.partner"].create({"name": "PRT C"}).id,
                "rating": 4,
                "consumed": True,
            }
        )
        editor = self._editor().create({})
        self.assertTrue(editor.enable_reviews)
        self.assertEqual(editor.review_count, 1)
        self.assertEqual(editor.review_avg, 4.0)
        self.assertTrue(editor.reviews_page_url.endswith(REVIEWS_PAGE_URL))

    def test_a_forged_company_shows_no_figures(self):
        self.stranger.enable_reviews = True
        editor = self._editor().create({})
        editor.company_id = self.stranger
        self.assertEqual(editor.review_count, 0)
        self.assertFalse(editor.reviews_page_url)

    def test_merchant_cannot_toggle_another_shop(self):
        editor = self._editor().create({"enable_reviews": True})
        editor.company_id = self.stranger
        with self.assertRaises(AccessError):
            editor.action_save()
        self.assertFalse(self.stranger.enable_reviews)
        self.assertFalse(self._reviews_menus(self.stranger))
        with self.assertRaises(AccessError):
            self._editor().with_context(
                microsite_company_id=self.stranger.id
            ).default_get(["enable_reviews"])

    def test_both_screens_carry_the_switch(self):
        company_arch = self.env["res.company"].get_views([(False, "form")])["views"][
            "form"
        ]["arch"]
        editor_arch = self.env["microsite.content.editor"].get_views([(False, "form")])[
            "views"
        ]["form"]["arch"]
        for arch in (company_arch, editor_arch):
            self.assertIn('name="reviews"', arch)
            self.assertIn('name="enable_reviews"', arch)
