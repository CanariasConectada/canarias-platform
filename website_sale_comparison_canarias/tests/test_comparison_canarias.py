# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestComparisonCanarias(HttpCase):
    """The compare button must reach products with NO variant attributes —
    the case core hides and this module exists to restore."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Creating a company on this platform trips website_sale_collect's
        # "the delivery method and a warehouse must share the same company":
        # the new company's warehouse meets an in_store delivery method that
        # is not its own. That blocks onboarding a merchant, not just this
        # test, and is reported separately; held open for the whole class
        # because the pending recompute is flushed again in every setUp.
        cls.startClassPatcher(
            patch.object(
                type(cls.env["delivery.carrier"]),
                "_check_warehouses_have_same_company",
                lambda self: None,
            )
        )
        cls.merchant = cls.env["res.company"].create({"name": "WSCC Tienda"})
        cls.env["website"].create(
            {
                "name": "WSCC",
                "company_id": cls.merchant.id,
                "domain": "https://wscc.example",
            }
        )
        cls.product = cls.env["product.template"].create(
            {
                "name": "WSCC Sin Variantes",
                "sale_ok": True,
                "is_published": True,
                "list_price": 12.0,
                "company_ids": [(6, 0, [cls.merchant.id])],
            }
        )
        cls.portal = cls.env["website"].search([], order="id", limit=1)
        cls.portal.is_marketplace = True

    def test_compare_button_shows_for_a_product_without_attributes(self):
        self.assertFalse(
            self.product.valid_product_template_attribute_line_ids,
            "el producto de prueba no debe tener atributos (es el caso a cubrir)",
        )
        # Searched by name rather than page one of /shop: on a copy of
        # production the aggregated shop holds 1576 products and a freshly
        # created one is nowhere near the first page.
        response = self.url_open("/shop?search=WSCC+Sin+Variantes")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wscc_compare_btn", response.text)
        self.assertIn(
            'data-product-product-id="%s"' % self.product.product_variant_id.id,
            response.text,
        )
