# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# The nine the retired role implied, read from the pre-uninstall snapshot.
MERCHANT_GROUPS = (
    "base.group_user",
    "base.group_multi_company",
    "website.group_website_restricted_editor",
    "sales_team.group_sale_salesman",
    "product.group_product_manager",
    "company_certification.group_silver_user",
    "company_certification.group_sustainability_user",
    "mass_mailing.group_mass_mailing_user",
    "partner_reviews.group_partner_reviews_user",
)


@tagged("post_install", "-at_install")
class TestMerchantGroup(TransactionCase):
    def test_the_group_carries_the_whole_merchant_set(self):
        merchant = self.env.ref("merchant_group.group_merchant")
        implied = set(merchant.implied_ids.ids)
        for xmlid in MERCHANT_GROUPS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self.env.ref(xmlid).id, implied)

    def test_ticking_it_is_the_whole_gesture(self):
        user = self.env["res.users"].create(
            {
                "name": "Merchant Group User",
                "login": "merchant_group_user",
                "group_ids": [(6, 0, [self.env.ref("merchant_group.group_merchant").id])],
            }
        )
        for xmlid in MERCHANT_GROUPS:
            with self.subTest(xmlid=xmlid):
                self.assertTrue(user.has_group(xmlid))

    def test_a_new_internal_user_is_a_merchant_by_default(self):
        """Core reads base.default_user_group.implied_ids in _default_groups."""
        self.assertIn(
            self.env.ref("merchant_group.group_merchant"),
            self.env.ref("base.default_user_group").implied_ids,
        )
        user = self.env["res.users"].create(
            {"name": "Fresh Internal", "login": "merchant_group_fresh"}
        )
        self.assertTrue(user.has_group("merchant_group.group_merchant"))
        self.assertTrue(user.has_group("website.group_website_restricted_editor"))

    def test_a_hand_granted_permission_survives_the_group(self):
        """A group is not a role: nothing is recomposed on write."""
        extra = self.env.ref("base.group_partner_manager")
        user = self.env["res.users"].create(
            {
                "name": "Merchant With Extra",
                "login": "merchant_group_extra",
                "group_ids": [
                    (4, self.env.ref("merchant_group.group_merchant").id),
                    (4, extra.id),
                ],
            }
        )
        user.write({"name": "Merchant With Extra, renamed"})
        self.assertIn(extra, user.all_group_ids)
