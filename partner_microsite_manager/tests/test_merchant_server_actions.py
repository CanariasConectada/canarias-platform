# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

NO_MAIL_CTX = {"no_reset_password": True, "mail_create_nolog": True, "mail_notrack": True}


@tagged("post_install", "-at_install")
class TestMerchantServerActions(TransactionCase):
    """A merchant runs the two code actions behind the Website menu.

    Odoo 19 refuses a code action to a user who can neither write its model
    nor is in one of its groups (reported as "Error de acceso" on
    2026-09-15). A merchant only reads res.company, so the group is what
    lets them in.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, **NO_MAIL_CTX))
        cls.company = cls.env["res.company"].create({"name": "Server Action Shop"})
        cls.website = cls.env["website"].create(
            {"name": "Server Action Shop site", "company_id": cls.company.id}
        )
        cls.merchant = cls.env["res.users"].create(
            {
                "name": "Server Action Merchant",
                "login": "server_action_merchant",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, cls.company.ids)],
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("website.group_website_restricted_editor").id),
                ],
            }
        )

    def _run(self, xmlid):
        action = self.env.ref(xmlid).with_user(self.merchant)
        return action.with_context(allowed_company_ids=self.company.ids).run()

    def test_a_merchant_cannot_write_companies(self):
        self.assertFalse(self.env["res.company"].with_user(self.merchant).has_access("write"))

    def test_my_shops_opens_for_a_merchant(self):
        result = self._run("partner_microsite_manager.action_own_websites")
        self.assertEqual(result.get("type"), "ir.actions.act_window")
        self.assertEqual(result.get("res_model"), "website")

    def test_page_content_opens_for_a_merchant(self):
        result = self._run("partner_microsite_manager.action_own_microsite_content")
        self.assertEqual(result.get("type"), "ir.actions.act_window")

    def test_the_row_and_button_actions_carry_views(self):
        """doAction on a raw action dict needs ``views``: a row click of My
        shops crashed without them (2026-09-16)."""
        site = self.website.with_user(self.merchant).with_context(
            allowed_company_ids=self.company.ids
        )
        for method in ("action_microsite_content", "action_microsite_pages"):
            with self.subTest(method=method):
                action = getattr(site, method)()
                self.assertTrue(action.get("views"), method)

    def test_my_sites_list_has_no_pages_button(self):
        """The client removed "Pages" from the merchant's list (2026-09-16)."""
        arch = self.env.ref("partner_microsite_manager.website_view_list_merchant").arch
        self.assertNotIn("action_microsite_pages", arch)
        self.assertIn("action_microsite_content", arch)

