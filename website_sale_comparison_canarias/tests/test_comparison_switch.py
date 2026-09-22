# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch
from urllib.parse import urlparse

from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale_comparison_canarias.controllers.main import (
    CANDIDATE_LIMIT,
)
from odoo.addons.website_sale_comparison_canarias.models.website import PARAM_ENABLED
from odoo.addons.website_sale_comparison_canarias.tests.common import (
    set_comparison_enabled,
)

# Every marker a compare control leaves in a page: this module's own classes,
# core's click hook (on its buttons and on ours), and the picker.
COMPARE_MARKERS = ("o_wscc_", 'data-action="o_comparelist"', "o_wscc_compare_modal")


@tagged("post_install", "-at_install")
class TestComparisonSwitch(HttpCase):
    """The platform switch: off means not rendered and not answered."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].browse(1)
        # Same stand-in as the candidates tests: on a bare database no
        # marketplace exists and the ON assertions about scopes would have
        # no site to answer from.
        if not cls.website._comparison_portal_website():
            cls.startClassPatcher(
                patch.object(
                    type(cls.env["website"]),
                    "_sync_marketplace_products",
                    lambda self: None,
                )
            )
            cls.website.is_marketplace = True
        cls.product = cls.env["product.template"].create(
            {
                "name": "WSCC Switch Product",
                "sale_ok": True,
                "is_published": True,
                "list_price": 15.0,
            }
        )

    def setUp(self):
        super().setUp()
        # Every test starts from the shipped state and says when it turns
        # the comparator on, so the order tests run in cannot matter.
        set_comparison_enabled(self.env, False)

    def _candidates(self, **params):
        response = self.opener.post(
            self.base_url() + "/shop/compare/candidates",
            json={
                "params": {"product_template_id": self.product.id, **params},
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
            },
        )
        return response.json()["result"]

    # ------------------------------------------------------------------
    # The switch itself
    # ------------------------------------------------------------------
    def test_shipped_parameter_is_the_switch(self):
        record = self.env.ref(
            "website_sale_comparison_canarias.param_comparison_enabled"
        )
        self.assertEqual(record.key, PARAM_ENABLED)

    def test_the_text_false_is_off(self):
        """The trap: a Boolean setting writes the STRING ``"False"``, which
        is truthy. The reader must parse it, not test it."""
        Param = self.env["ir.config_parameter"].sudo()
        for raw, expected in (
            ("False", False),
            ("True", True),
            ("0", False),
            ("1", True),
            ("", False),
            ("nonsense", False),
        ):
            Param.set_param(PARAM_ENABLED, raw)
            self.assertEqual(self.website._wscc_comparison_enabled(), expected, raw)
        Param.search([("key", "=", PARAM_ENABLED)]).unlink()
        self.assertFalse(self.website._wscc_comparison_enabled())

    def test_settings_field_round_trips(self):
        Settings = self.env["res.config.settings"]
        Settings.create({"wscc_comparison_enabled": True}).execute()
        self.assertTrue(self.website._wscc_comparison_enabled())
        self.assertTrue(Settings.create({}).wscc_comparison_enabled)
        Settings.create({"wscc_comparison_enabled": False}).execute()
        self.assertFalse(self.website._wscc_comparison_enabled())
        self.assertFalse(Settings.create({}).wscc_comparison_enabled)

    # ------------------------------------------------------------------
    # The endpoint
    # ------------------------------------------------------------------
    def test_endpoint_refuses_when_off(self):
        data = self._candidates(scope="all")
        self.assertIsNone(data["current"])
        self.assertEqual(data["products"], [])
        self.assertEqual(data["scopes"], [])
        self.assertEqual(data["categories"], [])
        self.assertEqual(data["total"], 0)
        # The shape the modal draws, in full: refusal is never an error.
        self.assertEqual(data["limit"], CANDIDATE_LIMIT)
        self.assertEqual(data["scope"], "all")
        self.assertEqual(data["zone"], "")

    def test_endpoint_answers_when_on(self):
        set_comparison_enabled(self.env, True)
        data = self._candidates()
        self.assertIsNotNone(data["current"])
        self.assertEqual(data["current"]["id"], self.product.id)
        self.assertTrue(data["scopes"])

    # ------------------------------------------------------------------
    # The pages
    # ------------------------------------------------------------------
    def _assert_no_compare_control(self, html, where):
        for marker in COMPARE_MARKERS:
            self.assertNotIn(
                marker, html, "%s left in %s with the switch off" % (marker, where)
            )

    def test_shop_listing_has_no_compare_control_when_off(self):
        response = self.url_open("/shop?search=WSCC+Switch+Product")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WSCC Switch Product", response.text)
        self._assert_no_compare_control(response.text, "the shop listing")

    def test_shop_listing_has_the_compare_control_when_on(self):
        set_comparison_enabled(self.env, True)
        response = self.url_open("/shop?search=WSCC+Switch+Product")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wscc_compare_btn", response.text)
        self.assertIn('data-action="o_comparelist"', response.text)
        self.assertIn('id="o_wscc_compare_modal"', response.text)

    def test_product_page_has_no_compare_control_when_off(self):
        response = self.url_open(self.product.website_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("WSCC Switch Product", response.text)
        self._assert_no_compare_control(response.text, "the product page")

    def test_product_page_has_the_compare_control_when_on(self):
        set_comparison_enabled(self.env, True)
        response = self.url_open(self.product.website_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wscc_compare_btn_picker", response.text)
        self.assertIn('id="o_wscc_compare_modal"', response.text)

    def test_comparison_page_is_sent_to_the_shop_when_off(self):
        """Followed to the end rather than read off the first hop: a site
        whose default language is not the visitor's answers with a language
        redirect first (``/en/shop/compare``), and only then with ours."""
        url = "/shop/compare?products=%s" % self.product.product_variant_id.id
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        path = urlparse(response.url).path.rstrip("/")
        self.assertTrue(
            path.endswith("/shop"), "sent to %r instead of the shop" % response.url
        )
        set_comparison_enabled(self.env, True)
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("/shop/compare", urlparse(response.url).path)
