# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestProductCardStyles(HttpCase):
    """The product card, asserted where a visitor meets it: in the bundle.

    Asked for on 2026-08-17 with a screenshot of a card on /shop: the border
    and the resting shadow out, the hover shadow out, and the layout tidied.

    Every assertion here is made against the compiled stylesheet rather than
    the source file, because the source file proves only that somebody wrote
    it. What decides how the card looks is whether the rule reached
    `web.assets_frontend`, and a stylesheet dropped from the manifest fails
    exactly nothing otherwise.
    """

    def setUp(self):
        super().setUp()
        self.css = self._frontend_css()

    def _frontend_css(self):
        page = self.url_open("/shop")
        self.assertEqual(page.status_code, 200)
        match = re.search(
            r'href="(/web/assets/[^"]*web\.assets_frontend[^"]*\.css)"', page.text
        )
        self.assertTrue(match, "the shop page has to load a frontend stylesheet")
        bundle = self.url_open(match.group(1))
        self.assertEqual(bundle.status_code, 200)
        return bundle.text

    def test_the_card_has_no_border_and_no_shadow_at_rest(self):
        """Odoo 19 builds these cards out of custom properties.

        Overriding `box-shadow` directly works until somebody picks a different
        layout option in the editor and the theme sets the variable again on a
        more specific selector, so the property is what has to be set.
        """
        for variable in (
            "--o-wsale-card-border-width: 0",
            "--o-wsale-card-shadow: none",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, self.css)

    def test_the_card_does_not_cast_a_shadow_on_hover_either(self):
        for variable in (
            "--o-wsale-card-shadow-hover: none",
            "--o-wsale-card-transform-hover: none",
            "--o-wsale-card-pseudobg-shadow-hover: none",
        ):
            with self.subTest(variable=variable):
                self.assertIn(variable, self.css)

    def test_the_photo_lost_its_grey_backdrop(self):
        """A product shot that did not fill its box read as a framed picture."""
        self.assertIn("--o-wsale-card-thumb-background: transparent", self.css)

    def test_pointing_at_a_card_still_does_something(self):
        """The affordance is the point, the shadow was only one way to give it.

        A card that answers nothing when you point at it reads as an image
        rather than as a link, so removing the shadow without putting anything
        in its place would trade one complaint for another.
        """
        self.assertIn(
            ".oe_product_cart:hover .oe_product_image_img_wrapper img", self.css
        )
        self.assertIn("transform: scale(1.03)", self.css)

    def test_keyboard_focus_keeps_a_real_outline(self):
        """A hover effect is not a focus ring, and never was."""
        self.assertIn(".oe_product_cart a:focus-visible", self.css)
        self.assertIn("outline-offset: 2px", self.css)

    def test_the_badge_and_the_compare_button_share_one_row(self):
        """They were stacked, each with its own margin.

        Three rows of chrome between a product's name and its price is what
        made the card feel cluttered. Asserted on the selector depth as well:
        Bootstrap's `mt-1`/`mb-1` sit on those elements, so a shallower rule
        would lose and the fix would be invisible.
        """
        rule = ".oe_product_cart .o_wsale_product_information_text .o_wsc_company_pill"
        self.assertIn(rule, self.css)
        self.assertIn(
            ".oe_product_cart .o_wsale_product_information_text .o_wscc_compare_wrap",
            self.css,
        )

    def test_titles_are_clamped_so_a_row_stays_a_row(self):
        """Names here run from "Palotes" to a sentence."""
        self.assertIn(".oe_product_cart .o_wsale_products_item_title", self.css)
        self.assertIn("line-clamp: 2", self.css)

    def test_reduced_motion_is_honoured(self):
        self.assertIn("prefers-reduced-motion", self.css)
