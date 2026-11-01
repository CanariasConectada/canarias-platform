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
        # Core's card button also sits behind the website builder's "Compare"
        # tile option (``website_sale.product_tile_element_visibility``: an
        # element whose class is not in the design classes is rendered for
        # editors only), and that option is off by default. Switched on here
        # so that the card assertions test THIS module's switch and not the
        # builder's.
        design = cls.website.shop_opt_products_design_classes or ""
        if "o_wsale_products_opt_has_comparison" not in design:
            cls.website.shop_opt_products_design_classes = (
                design + " o_wsale_products_opt_has_comparison"
            ).strip()
        # A product WITH variant attributes: the one case where core renders
        # its own compare buttons (card and product page) by itself, so the
        # two core overrides are actually exercised.
        attribute = cls.env["product.attribute"].create(
            {
                "name": "WSCC Switch Size",
                "value_ids": [(0, 0, {"name": "S"}), (0, 0, {"name": "M"})],
            }
        )
        cls.variants = cls.env["product.template"].create(
            {
                "name": "WSCC Switch Variants",
                "sale_ok": True,
                "is_published": True,
                "list_price": 25.0,
                "attribute_line_ids": [
                    (
                        0,
                        0,
                        {
                            "attribute_id": attribute.id,
                            "value_ids": [(6, 0, attribute.value_ids.ids)],
                        },
                    )
                ],
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
        self.assertNotIn(
            "data-wscc-comparison",
            html,
            "body marker left in %s with the switch off" % where,
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

    # Core's own card button, as core renders it (ours carries more classes,
    # so this literal matches core's alone) and its product-page button.
    CORE_CARD_BUTTON = 'class="btn o_add_compare"'
    CORE_PAGE_BUTTON = "o_add_compare_dyn"

    def test_core_card_button_of_a_variant_product_follows_the_switch(self):
        self.assertTrue(self.variants.valid_product_template_attribute_line_ids)
        url = "/shop?search=WSCC+Switch+Variants"
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("WSCC Switch Variants", response.text)
        self.assertNotIn(self.CORE_CARD_BUTTON, response.text)
        self._assert_no_compare_control(response.text, "the variant card")
        set_comparison_enabled(self.env, True)
        response = self.url_open(url)
        self.assertIn(self.CORE_CARD_BUTTON, response.text)
        self.assertIn("o_wscc_compare_btn", response.text)

    def test_core_product_page_button_of_a_variant_product_follows_the_switch(self):
        response = self.url_open(self.variants.website_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("WSCC Switch Variants", response.text)
        self.assertNotIn(self.CORE_PAGE_BUTTON, response.text)
        self._assert_no_compare_control(response.text, "the variant product page")
        set_comparison_enabled(self.env, True)
        response = self.url_open(self.variants.website_url)
        # Core's button, inside its CTA wrapper, with core's own hook.
        self.assertIn(self.CORE_PAGE_BUTTON, response.text)
        self.assertIn('data-action="o_comparelist"', response.text)
        self.assertIn('id="product_option_block"', response.text)
        self.assertIn("o_wscc_compare_btn_picker", response.text)

    def test_body_carries_the_marker_only_when_on(self):
        response = self.url_open("/shop")
        self.assertNotIn("data-wscc-comparison", response.text)
        set_comparison_enabled(self.env, True)
        response = self.url_open("/shop")
        self.assertIn('data-wscc-comparison="1"', response.text)

    # ------------------------------------------------------------------
    # The bottom bar, in a real browser
    # ------------------------------------------------------------------
    # Core mounts the bar from its ``ProductComparison`` interaction and the
    # bar draws the ``comparison_product_ids`` cookie, so a cookie holding two
    # products is what proves whether that interaction ran at all.
    BAR_READY = 'document.body.getAttribute("is-ready") === "true"'
    BAR_PRESENT = """
        (function () {
            const started = Date.now();
            const tick = () => {
                if (document.querySelector(".o_wsale_comparison_bottom_bar")) {
                    console.log("test successful");
                } else if (Date.now() - started > 8000) {
                    console.error("no comparison bottom bar mounted with the switch on");
                } else {
                    setTimeout(tick, 100);
                }
            };
            tick();
        })();
    """
    BAR_ABSENT = """
        setTimeout(() => {
            if (document.querySelector(".o_wsale_comparison_bottom_bar")) {
                console.error("comparison bottom bar mounted with the switch off");
            } else {
                console.log("test successful");
            }
        }, 2000);
    """

    def _browser_cookies(self):
        ids = (self.product | self.variants).mapped("product_variant_id").ids
        return {
            "comparison_product_ids": "[%s]" % ",".join(str(i) for i in ids),
            # The site's own default language, so that no language redirect
            # happens: on a multi-language database the browser's
            # ``Accept-Language`` would send every URL through ``/xx/``, and
            # the layout's service-worker registration then fails with a
            # console error ("script resource is behind a redirect"), which
            # the browser test counts as a failure of its own.
            "frontend_lang": self.website.default_lang_id.code,
        }

    def test_bottom_bar_does_not_mount_when_off(self):
        self.browser_js(
            "/shop",
            self.BAR_ABSENT,
            ready=self.BAR_READY,
            cookies=self._browser_cookies(),
        )

    def test_bottom_bar_mounts_when_on(self):
        set_comparison_enabled(self.env, True)
        self.browser_js(
            "/shop",
            self.BAR_PRESENT,
            ready=self.BAR_READY,
            cookies=self._browser_cookies(),
        )

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
