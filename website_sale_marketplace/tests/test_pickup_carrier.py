# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestShopPickupCarrier(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # auto_microsite_generator (co-installed in the full image) would give
        # every company created here a website of its own; the tests create
        # the websites themselves.
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.Carrier = cls.env["delivery.carrier"]

    def _shop(self, name, with_website=True, **website_vals):
        company = self.env["res.company"].create({"name": name})
        website = self.env["website"]
        if with_website:
            website = website.create(
                {"name": name, "company_id": company.id, **website_vals}
            )
        return company, website

    def _carriers(self, company):
        return self.Carrier.search([("company_id", "=", company.id)])

    def test_new_shop_website_gets_one_published_pickup_carrier(self):
        company, website = self._shop("Pickup Shop Alpha")
        carrier = self._carriers(company)
        self.assertEqual(len(carrier), 1)
        self.assertEqual(carrier.delivery_type, "in_store")
        self.assertTrue(carrier.is_published)
        self.assertEqual(carrier.website_id, website)
        self.assertEqual(carrier.fixed_price, 0.0)
        self.assertEqual(carrier.product_id.type, "service")
        self.assertFalse(carrier.product_id.sale_ok)
        self.assertEqual(carrier.product_id.company_ids, company)
        self.assertEqual(len(carrier.warehouse_ids), 1)
        self.assertEqual(carrier.warehouse_ids.company_id, company)
        self.assertEqual(carrier.warehouse_ids.partner_id, company.partner_id)

    def test_calling_twice_creates_nothing_more(self):
        company, website = self._shop("Pickup Shop Bravo")
        carrier = self._carriers(company)
        warehouses = self.env["stock.warehouse"].search_count(
            [("company_id", "=", company.id)]
        )
        again = company._ensure_shop_pickup_carrier(website=website)
        self.assertEqual(again, carrier)
        self.assertEqual(self._carriers(company), carrier)
        self.assertEqual(
            self.env["stock.warehouse"].search_count([("company_id", "=", company.id)]),
            warehouses,
        )

    def test_a_marketplace_company_gets_none(self):
        # The product backfill a new portal marketplace runs is not under test
        # and, on a populated database, rewrites the company of existing
        # carriers through their products; keep it out of the picture.
        with patch.object(
            type(self.env["website"]), "_sync_marketplace_products", lambda self: None
        ):
            company, website = self._shop("Pickup Zone Charlie", is_marketplace=True)
        self.assertFalse(self._carriers(company))
        self.assertFalse(company._ensure_shop_pickup_carrier())

    def test_a_company_without_website_gets_none(self):
        company, _website = self._shop("Pickup Delta", with_website=False)
        self.assertFalse(company._ensure_shop_pickup_carrier())
        self.assertFalse(self._carriers(company))

    def test_a_company_without_warehouse_gets_one(self):
        company, _website = self._shop("Pickup Echo", with_website=False)
        warehouses = self.env["stock.warehouse"].search(
            [("company_id", "=", company.id)]
        )
        # Detach rather than unlink: stock refuses to delete a warehouse whose
        # locations are in use, and only the company link matters here.
        warehouses.write({"active": False})
        website = self.env["website"].create(
            {"name": "Pickup Echo", "company_id": company.id}
        )
        carrier = self._carriers(company)
        self.assertEqual(len(carrier), 1)
        self.assertTrue(carrier.warehouse_ids.active)
        self.assertNotIn(carrier.warehouse_ids, warehouses)
        self.assertEqual(carrier.warehouse_ids.partner_id, company.partner_id)
        self.assertEqual(carrier.website_id, website)

    def test_the_shop_checkout_offers_the_pickup_method(self):
        company, website = self._shop("Pickup Shop Foxtrot")
        carrier = self._carriers(company)
        partner = self.env["res.partner"].create({"name": "Pickup Buyer"})
        order = (
            self.env["sale.order"]
            .with_company(company)
            .create(
                {
                    "partner_id": partner.id,
                    "company_id": company.id,
                    "website_id": website.id,
                }
            )
        )
        methods = order.with_context(website_id=website.id)._get_delivery_methods()
        self.assertIn(carrier, methods)
