# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests import HttpCase, TransactionCase, tagged

# What Odoo ships, and leaves untranslated in its Spanish catalogue.
ODOO_HEADINGS = ("Alternative Products", "These other products might interest you")

RECOMMENDED_LIMIT_PARAM = "shop_frontend_tweaks.recommended_limit"


@tagged("post_install", "-at_install")
class TestRecommendedProducts(HttpCase):
    """The carousel itself is Odoo's (website_sale.alternative_products, active
    by default); what this module owns is the wording, the colour, and -- since
    the hybrid engine -- filling it in when a shop curated no alternatives.

    These cases pin the wording/colour on the curated path, which renders the
    same band the auto path does. The band is fetched over HTTP rather than
    rendered directly: the product template reads `combination_info` and friends
    out of a context that only the website controller builds.
    """

    def setUp(self):
        super().setUp()
        self.companion = self.env["product.template"].create(
            {"name": "Recommended companion", "is_published": True}
        )

    def _page(self):
        """A product page whose carousel is populated (curated alternatives)."""
        product = self.env["product.template"].create(
            {
                "name": "Main product",
                "is_published": True,
                "alternative_product_ids": [(6, 0, self.companion.ids)],
            }
        )
        response = self.url_open(product.website_url)
        self.assertEqual(response.status_code, 200)
        return response.text

    def _expected_heading(self):
        """The heading reaches the visitor in the website's language."""
        website = self.env["website"].search([], limit=1)
        code = website.default_lang_id.code
        return "También te recomendamos" if code == "es_ES" else "You may also like"

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
        """The title gets our branding hook. The colour itself lives in the
        web.assets_frontend bundle (static/src/css/recommended.css), not an
        inline <style>, so we assert on the class the stylesheet brands, not a
        raw hex in the DOM."""
        self.assertIn("shop-recommended-title", self._page())


@tagged("post_install", "-at_install")
class TestRecommendedEngine(TransactionCase):
    """The hybrid recommendation engine (models/product_template.py).

    Curated alternatives are an explicit override; absent them, a product
    recommends other published products from the SAME shop, never across shops.
    Assertions use membership (in / not-in), never equality against a full
    search, so ambient catalogue data cannot make them flap.
    """

    def setUp(self):
        super().setUp()
        # A production-sized copy already has many products; with the default
        # limit of 8 they crowd freshly created fixtures out of the result and
        # membership assertions flap. Raise the cap so the engine returns the
        # full bucket; the limit test overrides it locally.
        self.env["ir.config_parameter"].sudo().set_param(RECOMMENDED_LIMIT_PARAM, "500")
        # Fixtures are created the way merchants create them in production:
        # owned by a real (non-marketplace) company. website_sale_marketplace's
        # create hook then links the portal marketplace company on top, exactly
        # as it does live -- the tests exercise that final shape on purpose.
        website_model = self.env["website"]
        if "is_marketplace" in website_model._fields:
            self.marketplace_companies = (
                website_model.sudo().search([("is_marketplace", "=", True)]).company_id
            )
        else:
            self.marketplace_companies = self.env["res.company"].browse()
        merchants = self.env["res.company"].search(
            [("id", "not in", self.marketplace_companies.ids)], limit=2, order="id"
        )
        if len(merchants) < 2:
            self.skipTest("needs two non-marketplace merchant companies")
        self.merchant_a, self.merchant_b = merchants[0], merchants[1]
        self.main = self._product("CC engine main", self.merchant_a)
        self.sibling = self._product("CC engine sibling", self.merchant_a)

    def _product(self, name, company=None):
        vals = {"name": name, "is_published": True}
        # None -> a deliberately global/shared product (no company at all);
        # the marketplace create hook leaves those untouched.
        vals["company_ids"] = [(6, 0, company.ids)] if company else [(6, 0, [])]
        return self.env["product.template"].create(vals)

    def test_curated_alternatives_win(self):
        """A shop that curated alternatives keeps full control: the auto
        fallback must not run and must not add same-shop siblings."""
        curated = self._product("CC engine curated", self.merchant_a)
        self.main.alternative_product_ids = [(6, 0, curated.ids)]
        recs = self.main._get_website_alternative_product()
        self.assertEqual(recs, curated)
        self.assertNotIn(self.sibling, recs)

    def test_auto_fallback_recommends_same_shop(self):
        """No curation -> other published products of the same merchant."""
        recs = self.main._get_website_alternative_product()
        self.assertIn(self.sibling, recs)

    def test_never_recommends_itself(self):
        self.assertNotIn(self.main, self.main._get_website_alternative_product())

    def test_isolation_across_shops(self):
        """Another merchant's catalogue must never surface -- even though BOTH
        products carry the portal marketplace company after the create hook,
        which is precisely why the anchor is the owning merchant and not the
        website's company."""
        foreign = self._product("CC engine foreign", self.merchant_b)
        self.assertNotIn(foreign, self.main._get_website_alternative_product())

    def test_marketplace_scope_is_not_a_merchant(self):
        """A product living ONLY in marketplace companies has no shop: it must
        get no auto recommendations at all, never someone else's catalogue."""
        if not self.marketplace_companies:
            self.skipTest("no marketplace companies on this database")
        orphan = self._product(
            "CC engine marketplace-only", self.marketplace_companies[0]
        )
        self.assertFalse(orphan._get_website_alternative_product())

    def test_shared_products_recommend_shared(self):
        """Global products (no company) stay in the global bucket: they see
        other shared products, never a merchant's catalogue."""
        shared_a = self._product("CC engine shared A")
        shared_b = self._product("CC engine shared B")
        recs = shared_a._get_website_alternative_product()
        self.assertIn(shared_b, recs)
        self.assertNotIn(self.main, recs)

    def test_limit_is_configurable(self):
        self.env["ir.config_parameter"].sudo().set_param(RECOMMENDED_LIMIT_PARAM, "1")
        recs = self.main._get_website_alternative_product()
        self.assertLessEqual(len(recs), 1)

    def test_limit_falls_back_on_garbage(self):
        """A non-numeric parameter must not crash the product page."""
        self.env["ir.config_parameter"].sudo().set_param(
            RECOMMENDED_LIMIT_PARAM, "not-a-number"
        )
        self.assertEqual(self.main._cc_recommended_limit(), 8)
