# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

CORE_VIEWS = ("website_sale.reduction_code",)
LOYALTY_VIEWS = (
    "website_sale_loyalty.modify_code_form",
    "website_sale_loyalty.reduction_coupon_code",
    "website_sale_loyalty.cart_summary_inherit_website_gift_card_sale",
    "website_sale_loyalty.website_sale_purchased_gift_card",
    "website_sale_loyalty.sale_coupon_result",
)


@tagged("post_install", "-at_install")
class TestNoGiftCard(TransactionCase):
    """Nothing in the shop asks for a code that does not exist."""

    def test_the_promo_row_is_off(self):
        for xmlid in CORE_VIEWS:
            with self.subTest(xmlid=xmlid):
                self.assertFalse(self.env.ref(xmlid).active)

    def test_the_gift_card_views_are_off_when_loyalty_is_installed(self):
        for xmlid in LOYALTY_VIEWS:
            view = self.env.ref(xmlid, raise_if_not_found=False)
            if not view:
                continue  # website_sale_loyalty is not installed here
            with self.subTest(xmlid=xmlid):
                self.assertFalse(view.active)

    def test_the_words_are_gone_from_the_cart_drawer(self):
        arch = self.env.ref("website_sale.checkout_layout").get_combined_arch()
        self.assertNotIn("Gift card", arch)
        self.assertNotIn("Promo-code", arch)
