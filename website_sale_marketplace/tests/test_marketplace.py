# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase, new_test_user


class MarketplaceCommon:
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # auto_microsite_generator (co-installed in the full image) would create
        # a website per company on create; disable it for determinism.
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.website = cls.env.ref("website.default_website")
        cls.mp_company = cls.website.company_id or cls.env.company
        cls.company_b = cls.env["res.company"].create({"name": "MP Merchant B"})
        cls.company_c = cls.env["res.company"].create({"name": "MP Merchant C"})
        cls.prod_main = cls._make_product("MP Widget Main", cls.mp_company)
        cls.prod_b = cls._make_product("MP Widget Bravo", cls.company_b)
        cls.prod_b_hidden = cls._make_product(
            "MP Widget Hidden", cls.company_b, published=False
        )

    @classmethod
    def _make_product(cls, name, company, published=True):
        return cls.env["product.template"].create(
            {
                "name": name,
                "sale_ok": True,
                "is_published": published,
                "list_price": 12.0,
                "company_ids": [(6, 0, company.ids)],
            }
        )


@tagged("post_install", "-at_install")
class TestMarketplaceSync(MarketplaceCommon, TransactionCase):
    def test_marking_marketplace_backfills_products(self):
        self.assertNotIn(self.mp_company, self.prod_b.company_ids)
        self.website.is_marketplace = True
        # The marketplace company is now an extra visibility scope on every
        # product, without displacing the merchant company.
        self.assertIn(self.mp_company, self.prod_b.company_ids)
        self.assertIn(self.company_b, self.prod_b.company_ids)

    def test_new_product_gets_marketplace_company(self):
        self.website.is_marketplace = True
        fresh = self._make_product("MP Widget Fresh", self.company_b)
        self.assertIn(self.mp_company, fresh.company_ids)
        self.assertIn(self.company_b, fresh.company_ids)

    def test_isolation_between_merchants_preserved(self):
        self.website.is_marketplace = True
        # A company-C user must NOT see company-B's product even though it is
        # now also scoped to the marketplace company.
        user_c = new_test_user(
            self.env,
            login="mp_user_c",
            groups="base.group_user",
            company_id=self.company_c.id,
            company_ids=[(6, 0, self.company_c.ids)],
        )
        visible = (
            self.env["product.template"]
            .with_user(user_c)
            .search([("id", "=", self.prod_b.id)])
        )
        self.assertFalse(visible)


@tagged("post_install", "-at_install")
class TestMarketplaceShop(MarketplaceCommon, HttpCase):
    def test_shop_aggregates_cross_company(self):
        self.website.is_marketplace = True
        res = self.url_open("/shop?search=MP+Widget")
        self.assertEqual(res.status_code, 200)
        self.assertIn("MP Widget Main", res.text)
        self.assertIn("MP Widget Bravo", res.text)  # cross-company
        self.assertNotIn("MP Widget Hidden", res.text)  # no unpublished leak

    def test_shop_isolated_when_not_marketplace(self):
        self.website.is_marketplace = False
        res = self.url_open("/shop?search=MP+Widget")
        self.assertEqual(res.status_code, 200)
        self.assertIn("MP Widget Main", res.text)
        self.assertNotIn("MP Widget Bravo", res.text)

    def test_product_detail_cross_company(self):
        self.website.is_marketplace = True
        res = self.url_open(self.prod_b.website_url)
        self.assertEqual(res.status_code, 200)
        self.assertIn("MP Widget Bravo", res.text)
