# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


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
