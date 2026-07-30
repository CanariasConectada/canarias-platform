# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests import HttpCase, tagged

# What Odoo ships, and leaves untranslated in its Spanish catalogue.
ODOO_HEADINGS = ("Alternative Products", "These other products might interest you")


@tagged("post_install", "-at_install")
class TestRecommendedProducts(HttpCase):
    """The carousel itself is Odoo's (website_sale.alternative_products, active
    by default); what this module owns is the wording and the colour.

    The page is fetched over HTTP rather than rendered directly: the product
    template reads `combination_info` and friends out of a context that only the
    website controller builds.
    """

    def setUp(self):
        super().setUp()
        self.companion = self.env["product.template"].create(
            {"name": "Recommended companion", "is_published": True}
        )

    def _page(self, alternatives=True):
        vals = {"name": "Main product", "is_published": True}
        if alternatives:
            vals["alternative_product_ids"] = [(6, 0, self.companion.ids)]
        product = self.env["product.template"].create(vals)
        response = self.url_open(product.website_url)
        self.assertEqual(response.status_code, 200)
        return response.text

    def _expected_heading(self):
        """The heading reaches the visitor in the website's language."""
        website = self.env["website"].search([], limit=1)
        code = website.default_lang_id.code
        return "También te recomendamos" if code == "es_ES" else "You may also like"

    def test_block_only_appears_with_recommendations(self):
        """No recommendations set means no empty band on the page."""
        self.assertNotIn("o_wsale_alternative_products", self._page(alternatives=False))

    def test_block_appears_with_recommendations(self):
        self.assertIn("o_wsale_alternative_products", self._page())

    def test_odoo_wording_is_replaced(self):
        """ "Alternative" is the wrong word for a directory of independent local
        shops, and Odoo leaves both of its strings untranslated in es_ES."""
        html = self._page()
        for heading in ODOO_HEADINGS:
            self.assertNotIn(heading, html)

    def test_our_heading_reaches_the_visitor(self):
        self.assertIn(self._expected_heading(), self._page())

    def test_title_carries_the_platform_colour(self):
        html = self._page()
        self.assertIn("shop-recommended-title", html)
        self.assertIn("#714B67", html)
