# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestShopDesign(HttpCase):
    """The aggregated shop's look and its AJAX endpoint, over real HTTP.

    Run with a dbfilter that matches the test database: inside a deployment
    container the config pins the HTTP layer to the production database and
    every assertion silently reads the wrong site.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["product.public.category"].create(
            {"name": "WSC Alimentación"}
        )
        cls.merchant = cls.env["res.company"].create({"name": "WSC Panadería SL"})
        cls.merchant_site = cls.env["website"].create(
            {
                "name": "WSC Panadería",
                "company_id": cls.merchant.id,
                "domain": "https://wsc-panaderia.example",
            }
        )
        cls.product = cls.env["product.template"].create(
            {
                "name": "WSC Pan de Millo",
                "sale_ok": True,
                "is_published": True,
                "list_price": 25.0,
                "company_ids": [(6, 0, [cls.merchant.id])],
                "public_categ_ids": [(6, 0, [cls.category.id])],
            }
        )
        # The portal is flagged AFTER the product exists so the marketplace
        # backfill links it — the same order the live platform went through.
        cls.portal = cls.env["website"].search([], order="id", limit=1)
        cls.portal.is_marketplace = True

    # ------------------------------------------------------------------
    # The page
    # ------------------------------------------------------------------

    def test_portal_shop_wears_the_canarias_design(self):
        """Hero on, stock toolbar off, sidebar select on — the three moves
        that turn Odoo's shop into the platform's shop."""
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tienda Canarias Conectada", response.text)
        self.assertIn("wsc_category_select", response.text)
        self.assertNotIn('id="o_wsale_products_header"', response.text)

    def test_portal_card_names_the_merchant(self):
        """An aggregated shop sells nothing itself: every card must say
        whose shop window it is."""
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wsc_pill_badge", response.text)
        self.assertIn("WSC Panadería SL", response.text)

    def test_sidebar_offers_the_shop_categories(self):
        self.assertIn(self.category, self.portal._wsc_shop_categories())
        response = self.url_open("/shop")
        self.assertIn("WSC Alimentación", response.text)

    # ------------------------------------------------------------------
    # The AJAX endpoint
    # ------------------------------------------------------------------

    def _ajax(self, query=""):
        response = self.url_open("/shop/ajax/products" + query)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.text)

    def test_ajax_lists_the_published_product(self):
        result = self._ajax()
        self.assertNotIn("error", result)
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("WSC Pan de Millo", result["html"])

    def test_ajax_filters_by_category_search_and_price(self):
        by_category = self._ajax("?category=%s" % self.category.id)
        self.assertIn("WSC Pan de Millo", by_category["html"])
        self.assertTrue(by_category["filters_active"])
        self.assertEqual(by_category["category_name"], "WSC Alimentación")

        no_match = self._ajax("?search=zzz-nada-zzz")
        self.assertEqual(no_match["count"], 0)
        self.assertIn("No se encontraron productos", no_match["html"])

        priced_out = self._ajax("?min_price=1000")
        self.assertNotIn("WSC Pan de Millo", priced_out["html"])

    def test_ajax_links_the_card_to_the_merchants_site(self):
        result = self._ajax()
        self.assertIn("https://wsc-panaderia.example/shop/", result["html"])

    def test_ajax_on_a_microsite_does_not_leak_other_merchants(self):
        """The endpoint searches as the public user, so the record rule — not
        the domain alone — bounds a microsite to its own catalogue. A second
        merchant's published product must never reach the first's shop AJAX.
        """
        other = self.env["res.company"].create({"name": "WSC Otra SL"})
        other_site = self.env["website"].create(
            {"name": "WSC Otra", "company_id": other.id,
             "domain": "https://wsc-otra.example"}
        )
        self.env["product.template"].create({
            "name": "WSC Producto Ajeno",
            "sale_ok": True,
            "is_published": True,
            "list_price": 7.0,
            "company_ids": [(6, 0, [other.id])],
        })
        response = self.url_open(
            "/shop/ajax/products", headers={"Host": "wsc-panaderia.example"}
        )
        body = json.loads(response.text)
        self.assertNotIn("WSC Producto Ajeno", body["html"])
        self.assertIn("WSC Pan de Millo", body["html"])

    def test_ajax_excludes_products_of_an_archived_merchant(self):
        """An archived merchant's catalogue must not come back through AJAX
        even on the aggregating portal — the record rule hides it once the
        marketplace links are gone, and the endpoint honours the rule."""
        gone = self.env["res.company"].create({"name": "WSC Retirada SL"})
        self.env["product.template"].create({
            "name": "WSC Producto Retirado",
            "sale_ok": True,
            "is_published": True,
            "list_price": 3.0,
            "company_ids": [(6, 0, [gone.id])],
        })
        gone.active = False
        result = self._ajax()
        self.assertNotIn("WSC Producto Retirado", result["html"])

    # ------------------------------------------------------------------
    # A merchant microsite keeps its plain shop
    # ------------------------------------------------------------------

    def test_microsite_gets_no_hero_and_no_badge(self):
        response = self.url_open(
            "/shop", headers={"Host": "wsc-panaderia.example"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Tienda Canarias Conectada", response.text)
        self.assertNotIn("o_wsc_pill_badge", response.text)
