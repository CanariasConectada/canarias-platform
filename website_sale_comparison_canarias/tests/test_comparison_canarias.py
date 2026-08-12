# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestComparisonCanarias(HttpCase):
    """The compare button must reach products with NO variant attributes —
    the case core hides and this module exists to restore."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchant = cls.env["res.company"].create({"name": "WSCC Tienda"})
        cls.env["website"].create({
            "name": "WSCC", "company_id": cls.merchant.id,
            "domain": "https://wscc.example",
        })
        cls.product = cls.env["product.template"].create({
            "name": "WSCC Sin Variantes",
            "sale_ok": True,
            "is_published": True,
            "list_price": 12.0,
            "company_ids": [(6, 0, [cls.merchant.id])],
        })
        cls.portal = cls.env["website"].search([], order="id", limit=1)
        cls.portal.is_marketplace = True

    def test_compare_button_shows_for_a_product_without_attributes(self):
        self.assertFalse(
            self.product.valid_product_template_attribute_line_ids,
            "el producto de prueba no debe tener atributos (es el caso a cubrir)",
        )
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wscc_compare_btn", response.text)
        self.assertIn(
            'data-product-product-id="%s"' % self.product.product_variant_id.id,
            response.text,
        )
