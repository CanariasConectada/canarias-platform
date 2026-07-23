# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo import fields
from odoo.tests import tagged
from odoo.tests.common import HttpCase, TransactionCase, new_test_user

from odoo.addons.website_sale_marketplace.models import website as website_model


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
    def _spy_company_ids_writes(self):
        """Patch product.template.write to record every write touching
        ``company_ids``. Returns ``(patcher, calls)`` where ``calls`` is a
        list with one entry (the written product ids) per write call, so
        tests can also assert how the backfill batches its writes."""
        Product = self.env.registry["product.template"]
        calls = []
        origin_write = Product.write

        def write_spy(records, vals):
            if "company_ids" in vals:
                calls.append(records.ids)
            return origin_write(records, vals)

        return patch.object(Product, "write", write_spy), calls

    def _make_fresh_marketplace(self, name):
        """Company + website pair no existing product is linked to yet.

        On a production copy the database can already contain a live
        marketplace website whose company was linked to every product (at
        backfill time or by the create hook), so backfill assertions must
        target a brand-new company instead of an existing one.
        """
        company = self.env["res.company"].create({"name": name})
        website = self.env["website"].create({"name": name, "company_id": company.id})
        return company, website

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

    def test_backfill_writes_only_missing_products(self):
        # Use a fresh company so no product can be pre-linked (the create
        # hook links every EXISTING marketplace company at product create,
        # so an existing company would leave nothing to backfill).
        fresh_company, fresh_website = self._make_fresh_marketplace("MP Fresh Sync Co")
        # prod_b is linked by hand: it must NOT receive a backfill write.
        self.prod_b.company_ids = [fields.Command.link(fresh_company.id)]
        spy, calls = self._spy_company_ids_writes()
        with spy:
            fresh_website.is_marketplace = True
        written_ids = [pid for ids in calls for pid in ids]
        self.assertNotIn(self.prod_b.id, written_ids)
        self.assertIn(self.prod_b_hidden.id, written_ids)
        self.assertIn(fresh_company, self.prod_b_hidden.company_ids)
        self.assertIn(fresh_company, self.prod_b.company_ids)
        # Re-syncing an already synced marketplace touches no product at all.
        spy, calls = self._spy_company_ids_writes()
        with spy:
            fresh_website._sync_marketplace_products()
        self.assertFalse(calls)

    def test_backfill_batched_writes_same_end_state(self):
        fresh_company, fresh_website = self._make_fresh_marketplace("MP Fresh Batch Co")
        extra_d = self._make_product("MP Widget Delta", self.company_b)
        extra_e = self._make_product("MP Widget Echo", self.company_c)
        tracked = (self.prod_b, self.prod_b_hidden, extra_d, extra_e)
        tracked_ids = {product.id for product in tracked}
        # Force one write per product: the batched backfill must reach the
        # same end state as a single global write.
        spy, calls = self._spy_company_ids_writes()
        with spy, patch.object(website_model, "BACKFILL_BATCH_SIZE", 1):
            fresh_website.is_marketplace = True
        for product in tracked:
            self.assertIn(fresh_company, product.company_ids)
        # Merchant companies are never displaced by the backfill.
        self.assertIn(self.company_b, self.prod_b.company_ids)
        self.assertIn(self.company_c, extra_e.company_ids)
        # The backfill issued one write call per batch (here: per product),
        # so the tracked products each arrived in a single-id write.
        our_calls = [ids for ids in calls if set(ids) & tracked_ids]
        self.assertEqual(len(our_calls), len(tracked))
        self.assertTrue(all(len(ids) == 1 for ids in our_calls))

    def test_toggle_off_keeps_existing_links(self):
        fresh_company, fresh_website = self._make_fresh_marketplace(
            "MP Fresh Toggle Co"
        )
        fresh_website.is_marketplace = True
        self.assertIn(fresh_company, self.prod_b.company_ids)
        # Toggling OFF has never had an inverse unlink; pin that the
        # backfilled links survive so the optimization adds no new semantics.
        fresh_website.is_marketplace = False
        self.assertIn(fresh_company, self.prod_b.company_ids)
        self.assertIn(self.company_b, self.prod_b.company_ids)

    def test_create_prelinked_product_skips_write(self):
        self.website.is_marketplace = True
        # Pre-link EVERY current marketplace company (a production copy may
        # already contain marketplace websites besides self.website).
        marketplace_companies = self.env["website"]._marketplace_companies()
        spy, calls = self._spy_company_ids_writes()
        with spy:
            prelinked = self._make_product(
                "MP Widget Prelinked", self.company_b | marketplace_companies
            )
        # Created with every marketplace company already linked: the create
        # hook must not issue a redundant company_ids write.
        written_ids = [pid for ids in calls for pid in ids]
        self.assertNotIn(prelinked.id, written_ids)
        self.assertIn(self.mp_company, prelinked.company_ids)
        self.assertIn(self.company_b, prelinked.company_ids)

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
