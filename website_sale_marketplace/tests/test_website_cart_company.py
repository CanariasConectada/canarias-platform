# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tests import tagged
from odoo.tests.common import TransactionCase, new_test_user

from odoo.addons.website_sale.tests.common import MockRequest


@tagged("post_install", "-at_install")
class TestWebsiteCartCompany(TransactionCase):
    """A shop sells to customers who belong to another company (a zone).

    ``website/models/ir_http.py`` runs a logged-in user's request with their
    own company when it is not the website's: a zone customer shopping on a
    merchant website of that zone. The cart, its delivery method and its
    confirmation must all be judged against the ORDER's company.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.zone = cls.env["res.company"].create({"name": "Cart Zone"})
        cls.shop = cls.env["res.company"].create({"name": "Cart Shop"})
        # Creating the website gives the shop its pickup carrier.
        cls.website = cls.env["website"].create(
            {"name": "Cart Shop", "company_id": cls.shop.id}
        )
        cls.carrier = cls.shop._ensure_shop_pickup_carrier(website=cls.website)
        cls.product = cls._product("Cart Salad", cls.shop | cls.zone)
        cls.zone_product = cls._product("Cart Zone Only", cls.zone)
        cls.customer = new_test_user(
            cls.env,
            login="cart_zone_customer",
            groups="base.group_portal",
            company_id=cls.zone.id,
            company_ids=[Command.set(cls.zone.ids)],
        )
        partner = cls.customer.partner_id
        # The production shape: the customer's partner is restricted to the
        # zone (partner_multi_company when installed, core company otherwise).
        if "company_ids" in partner._fields:
            partner.company_ids = [Command.set(cls.zone.ids)]
        else:
            partner.company_id = cls.zone

    @classmethod
    def _product(cls, name, companies):
        return cls.env["product.template"].create(
            {
                "name": name,
                "type": "consu",
                "sale_ok": True,
                "is_published": True,
                "list_price": 10.0,
                "company_ids": [Command.set(companies.ids)],
            }
        )

    def _shopper_env(self, user, company):
        # What ir_http gives the request of a user outside the website company.
        return self.env(
            user=user,
            context=dict(
                self.env.context,
                allowed_company_ids=company.ids,
                website_id=self.website.id,
            ),
        )

    def test_zone_customer_buys_on_the_shop(self):
        env = self._shopper_env(self.customer, self.zone)
        website = self.website.with_env(env)
        with MockRequest(env, website=website):
            order = website._create_cart()
            self.assertEqual(order.company_id, self.shop)
            order._cart_add(self.product.product_variant_id.id, 2)
            # The constraint as a write from the shopper's env triggers it.
            order._check_order_line_company_id()
            methods = order._get_delivery_methods()
            self.assertIn(self.carrier, methods)
            order._set_delivery_method(self.carrier)
            self.assertEqual(order.carrier_id, self.carrier)
            order.action_confirm()
            self.env.flush_all()
        self.assertEqual(order.state, "sale")
        partner = self.customer.partner_id.sudo()
        if "company_ids" in partner._fields:
            self.assertIn(self.shop, partner.company_ids)
            self.assertIn(self.zone, partner.company_ids)

    def test_website_flow_still_refuses_a_product_of_another_company(self):
        env = self._shopper_env(self.customer, self.zone)
        website = self.website.with_env(env)
        with MockRequest(env, website=website):
            order = website._create_cart()
            with self.assertRaises(UserError):
                order._cart_add(self.zone_product.product_variant_id.id, 1)

    def test_anonymous_cart_unchanged(self):
        public = self.website.user_id
        env = self.env(
            user=public,
            context=dict(
                self.env.context,
                allowed_company_ids=self.shop.ids,
                website_id=self.website.id,
            ),
        )
        website = self.website.with_env(env)
        with MockRequest(env, website=website):
            order = website._create_cart()
            order._cart_add(self.product.product_variant_id.id, 1)
            self.assertIn(self.carrier, order._get_delivery_methods())
        self.assertEqual(order.order_line.product_id, self.product.product_variant_id)

    def test_backend_keeps_core_company_checks(self):
        # No request: an internal user's order of the shop with a product
        # that is not linked to the shop is still refused (core raises either
        # the line's company inconsistency or the order's ValidationError,
        # both UserErrors).
        with self.assertRaises(UserError):
            self.env["sale.order"].with_company(self.shop).create(
                {
                    "partner_id": self.env["res.partner"].create({"name": "B"}).id,
                    "company_id": self.shop.id,
                    "order_line": [
                        Command.create(
                            {"product_id": self.zone_product.product_variant_id.id}
                        )
                    ],
                }
            )
        # And the customer exemption is website-only: the zone customer on a
        # backend order of the shop is still a company inconsistency.
        with self.assertRaises(UserError):
            self.env["sale.order"].with_company(self.shop).create(
                {
                    "partner_id": self.customer.partner_id.id,
                    "company_id": self.shop.id,
                    "website_id": self.website.id,
                }
            )
