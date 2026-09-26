# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

import importlib.util
import json
from os.path import join
from unittest.mock import patch

from odoo.modules.module import get_module_path
from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.website_sale_merchant_alert.models.sale_order import SaleOrder


@tagged("post_install", "-at_install")
class TestMerchantAlert(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Alert Shop"})
        cls.company.partner_id.email = "shop@alert.example.com"
        cls.staff = new_test_user(
            cls.env,
            login="alert_shop_staff",
            groups="base.group_user",
            company_id=cls.company.id,
            company_ids=[(6, 0, cls.company.ids)],
        )
        cls.website = cls.env["website"].create(
            {"name": "Alert Site", "company_id": cls.company.id}
        )
        cls.buyer = cls.env["res.partner"].create(
            {"name": "Buyer", "email": "buyer@example.com"}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "Alert Product", "list_price": 10.0}
        )
        cls.env["res.lang"]._activate_lang("es_ES")
        cls.staff.partner_id.lang = "es_ES"
        # A merchant whose main company is another shop.
        cls.other_company = cls.env["res.company"].create({"name": "Other Shop"})
        cls.allowed_staff = new_test_user(
            cls.env,
            login="alert_allowed_staff",
            groups="base.group_user",
            company_id=cls.other_company.id,
            company_ids=[(6, 0, (cls.company | cls.other_company).ids)],
        )
        cls.other_staff = new_test_user(
            cls.env,
            login="alert_other_staff",
            groups="base.group_user",
            company_id=cls.other_company.id,
            company_ids=[(6, 0, cls.other_company.ids)],
        )
        cls.platform_admin = new_test_user(
            cls.env,
            login="alert_platform_admin",
            groups="base.group_user,base.group_system",
            company_id=cls.other_company.id,
            company_ids=[(6, 0, (cls.company | cls.other_company).ids)],
        )
        cls.portal_user = new_test_user(
            cls.env,
            login="alert_portal",
            groups="base.group_portal",
            company_id=cls.company.id,
            company_ids=[(6, 0, cls.company.ids)],
        )
        config = cls.env["ir.config_parameter"].sudo()
        config.set_param("mail.web_push_vapid_private_key", "test-private")
        config.set_param("mail.web_push_vapid_public_key", "test-public")
        cls.devices = {}
        for user in (
            cls.staff,
            cls.allowed_staff,
            cls.other_staff,
            cls.platform_admin,
            cls.portal_user,
        ):
            cls.devices[user] = (
                cls.env["mail.push.device"]
                .sudo()
                .create(
                    {
                        "partner_id": user.partner_id.id,
                        "endpoint": f"https://push.example.com/{user.login}",
                        "keys": json.dumps({"p256dh": "x", "auth": "y"}),
                    }
                )
            )

    def _make_order(self, website=None):
        return (
            self.env["sale.order"]
            .with_company(self.company)
            .create(
                {
                    "partner_id": self.buyer.id,
                    "company_id": self.company.id,
                    "website_id": website.id if website else False,
                    "order_line": [
                        (0, 0, {"product_id": self.product.id, "product_uom_qty": 1})
                    ],
                }
            )
        )

    def test_website_order_alerts_the_shop(self):
        order = self._make_order(website=self.website)
        before = self.env["mail.mail"].sudo().search_count([])
        order.action_confirm()
        mails = self.env["mail.mail"].sudo().search([], order="id desc", limit=3)
        self.assertGreater(self.env["mail.mail"].sudo().search_count([]), before)
        self.assertTrue(
            any("shop@alert.example.com" in (m.email_to or "") for m in mails)
        )
        self.assertIn(self.staff.partner_id, order.message_partner_ids)

    def test_backend_order_stays_silent(self):
        order = self._make_order(website=None)
        order.action_confirm()
        mails = (
            self.env["mail.mail"]
            .sudo()
            .search([("email_to", "like", "shop@alert.example.com")])
        )
        self.assertFalse(mails)

    def test_a_mail_failure_never_breaks_the_checkout(self):
        order = self._make_order(website=self.website)
        self.env.ref(
            "website_sale_merchant_alert.mail_template_merchant_alert"
        ).sudo().unlink()
        order.action_confirm()
        self.assertEqual(order.state, "sale")

    def _pushes(self, user=None):
        domain = [("payload", "like", "order-")]
        if user:
            domain.append(("mail_push_device_id", "=", self.devices[user].id))
        return self.env["mail.push"].sudo().search(domain)

    def test_confirmed_website_order_pushes_the_shop_in_its_language(self):
        order = self._make_order(website=self.website)
        with patch.object(
            type(self.env["mail.thread"]), "_web_push_send_notification"
        ) as direct:
            order.action_confirm()
        direct.assert_not_called()  # queued, never sent inside the checkout
        self.assertTrue(order.merchant_alert_sent)
        push = self._pushes(self.staff)
        self.assertEqual(len(push), 1)
        payload = json.loads(push.payload)
        self.assertEqual(payload["title"], f"Nuevo pedido {order.name}")
        self.assertIn("Alert Shop", payload["options"]["body"])
        self.assertIn("Buyer", payload["options"]["body"])
        self.assertIn("10,00", payload["options"]["body"])
        self.assertEqual(payload["options"]["tag"], f"order-{order.id}")
        self.assertTrue(payload["options"]["renotify"])
        self.assertFalse(payload["options"]["silent"])
        self.assertFalse(payload["options"]["requireInteraction"])
        self.assertTrue(payload["options"]["icon"])
        data = payload["options"]["data"]
        self.assertEqual((data["model"], data["res_id"]), ("sale.order", order.id))
        self.assertEqual(data["url"], f"/odoo/orders/{order.id}")
        # A merchant who has the shop as an allowed company hears too.
        self.assertTrue(self._pushes(self.allowed_staff))
        self.assertEqual(
            order.message_partner_ids
            & (
                self.staff
                | self.allowed_staff
                | self.other_staff
                | self.platform_admin
                | self.portal_user
            ).partner_id,
            (self.staff | self.allowed_staff).partner_id,
        )

    def test_other_companies_admins_and_portal_get_nothing(self):
        order = self._make_order(website=self.website)
        order.action_confirm()
        self.assertTrue(self._pushes(self.staff))
        self.assertFalse(self._pushes(self.other_staff))
        self.assertFalse(self._pushes(self.platform_admin))
        self.assertFalse(self._pushes(self.portal_user))

    def test_backend_order_does_not_push(self):
        order = self._make_order(website=None)
        order.action_confirm()
        self.assertFalse(order.merchant_alert_sent)
        self.assertFalse(self._pushes())

    def test_a_push_failure_never_breaks_the_confirmation(self):
        order = self._make_order(website=self.website)
        with (
            patch.object(
                SaleOrder, "_merchant_alert_push_payload", side_effect=RuntimeError
            ),
            self.assertLogs(
                "odoo.addons.website_sale_merchant_alert.models.sale_order", "ERROR"
            ),
        ):
            order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertFalse(self._pushes())
        # The mail went out all the same.
        self.assertTrue(
            self.env["mail.mail"]
            .sudo()
            .search([("email_to", "like", "shop@alert.example.com")])
        )

    def test_no_double_alert(self):
        order = self._make_order(website=self.website)
        order.action_confirm()
        order._action_cancel()
        order.action_draft()
        order.action_confirm()
        self.assertEqual(len(self._pushes(self.staff)), 1)

    def test_payment_that_leaves_a_quotation_alerts_once(self):
        order = self._make_order(website=self.website)
        # Built like payment's own PaymentCommon: the "unknown" method is
        # shipped by payment itself (archived, so a search would miss it)
        # and exists on any database, fresh CI ones included.
        method = self.env.ref("payment.payment_method_unknown")
        provider = self.env["payment.provider"].create(
            {
                "name": "Test transfer",
                "code": "none",
                "state": "test",
                "company_id": self.company.id,
                "payment_method_ids": [(6, 0, method.ids)],
            }
        )
        tx = self.env["payment.transaction"].create(
            {
                "provider_id": provider.id,
                "payment_method_id": method.id,
                "amount": order.amount_total,
                "currency_id": order.currency_id.id,
                "partner_id": self.buyer.id,
                "reference": f"{order.name}-test",
                "sale_order_ids": [(6, 0, order.ids)],
                "state": "pending",
            }
        )
        tx._post_process()
        self.assertNotEqual(order.state, "sale")
        self.assertTrue(order.merchant_alert_sent)
        self.assertEqual(len(self._pushes(self.staff)), 1)
        order.action_confirm()
        self.assertEqual(len(self._pushes(self.staff)), 1)

    def test_a_failed_alert_is_retried_by_the_next_trigger(self):
        order = self._make_order(website=self.website)
        template_model = type(self.env["mail.template"])
        with (
            patch.object(template_model, "send_mail", side_effect=RuntimeError),
            self.assertLogs(
                "odoo.addons.website_sale_merchant_alert.models.sale_order", "ERROR"
            ),
        ):
            order.action_confirm()
        self.assertEqual(order.state, "sale")
        self.assertFalse(order.merchant_alert_sent)
        self.assertFalse(self._pushes())
        order._merchant_alert_once()
        self.assertTrue(order.merchant_alert_sent)
        self.assertEqual(len(self._pushes(self.staff)), 1)

    def test_flag_set_by_another_transaction_is_honoured(self):
        order = self._make_order(website=self.website)
        order.flush_recordset()
        # What a concurrent worker committed; this cache still says False.
        self.env.cr.execute(
            "UPDATE sale_order SET merchant_alert_sent = TRUE WHERE id = %s",
            (order.id,),
        )
        order._merchant_alert_once()
        self.assertFalse(self._pushes())

    def test_migration_marks_confirmed_and_cancelled_website_orders(self):
        path = join(
            get_module_path("website_sale_merchant_alert"),
            "migrations",
            "19.0.1.1.0",
            "post-migration.py",
        )
        spec = importlib.util.spec_from_file_location("wsma_post_migration", path)
        migration = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migration)
        confirmed = self._make_order(website=self.website)
        cancelled = self._make_order(website=self.website)
        cart = self._make_order(website=self.website)
        backend = self._make_order(website=None)
        (confirmed | cancelled | backend).action_confirm()
        cancelled._action_cancel()
        orders = confirmed | cancelled | cart | backend
        orders.flush_recordset()
        self.env.cr.execute(
            "UPDATE sale_order SET merchant_alert_sent = FALSE WHERE id IN %s",
            (tuple(orders.ids),),
        )
        migration.migrate(self.env.cr, "19.0.1.0.0")
        orders.invalidate_recordset(["merchant_alert_sent"])
        self.assertTrue(confirmed.merchant_alert_sent)
        self.assertTrue(cancelled.merchant_alert_sent)
        self.assertFalse(cart.merchant_alert_sent)
        self.assertFalse(backend.merchant_alert_sent)
