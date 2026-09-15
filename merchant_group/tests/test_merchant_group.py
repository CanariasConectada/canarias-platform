# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# The nine the retired role implied (19.0.1.0.0) plus the four of the
# default merchant profile (19.0.2.0.0).
MERCHANT_GROUPS = (
    "base.group_user",
    "base.group_multi_company",
    "website.group_website_restricted_editor",
    "sales_team.group_sale_salesman",
    "product.group_product_manager",
    "product.group_product_variant",
    "company_certification.group_silver_user",
    "company_certification.group_sustainability_user",
    "mass_mailing.group_mass_mailing_user",
    "partner_reviews.group_partner_reviews_user",
    "purchase.group_purchase_user",
    "stock.group_stock_user",
    "account.group_account_invoice",
)

# Root menus a merchant sees, by xmlid. `training_menu` is not a
# dependency of this module: its entry is skipped when it is absent.
VISIBLE_ROOT_MENUS = (
    "mail.menu_root_discuss",
    "calendar.mail_menu_calendar",
    "project_todo.menu_todo_todos",
    "contacts.menu_contacts",
    "partner_reviews.menu_partner_reviews_root",
    "sale.sale_menu_root",
    "company_certification.menu_certification_root",
    "website.menu_website_configuration",
    "training_menu.menu_training_root",
    "mass_mailing.mass_mailing_menu_root",
    "crm.crm_menu_root",
    "purchase.menu_purchase_root",
    "stock.menu_stock_root",
    "account.menu_finance",
)
VISIBLE_INNER_MENUS = (
    "website_sale.menu_ecommerce",
    "sale.menu_products",
    "sale_loyalty.menu_discount_loyalty_type_config",
    "website_sale_loyalty.menu_loyalty",
    "website_sale_loyalty.menu_discount_loyalty_type_config",
)
HIDDEN_MENUS = (
    "project.menu_main_pm",
    "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
    "board.menu_board_my_dash",
    "merchant_group.menu_merchant_dashboard_root",
    "sale_loyalty.menu_gift_ewallet_type_config",
    "website_sale_loyalty.menu_gift_ewallet_type_config",
    "base.menu_management",
)


@tagged("post_install", "-at_install")
class TestMerchantGroup(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchant_group = cls.env.ref("merchant_group.group_merchant")
        cls.dashboard_group = cls.env.ref("merchant_group.group_merchant_dashboard")
        cls.company = cls.env.company
        cls.merchant = cls.env["res.users"].create(
            {
                "name": "Merchant Group User",
                "login": "merchant_group_user",
                "company_id": cls.company.id,
                "company_ids": [(6, 0, [cls.company.id])],
                "group_ids": [(6, 0, [cls.merchant_group.id])],
            }
        )

    def _visible_ids(self, user):
        """What load_menus() ends up showing: _visible_menu_ids() keeps a
        menu whose own gate passes even when an ancestor's does not, and
        load_menus() then drops every branch not attached to a root."""
        Menu = self.env["ir.ui.menu"].with_user(user)
        passing = set(Menu._visible_menu_ids())
        parent_of = {m.id: m.parent_id.id for m in Menu.sudo().browse(list(passing))}
        attached = set()
        for menu_id in passing:
            chain = []
            current = menu_id
            while current and current in passing:
                chain.append(current)
                current = parent_of[current]
            if not current:
                attached.update(chain)
        return attached

    def _menu(self, xmlid):
        menu = self.env.ref(xmlid, raise_if_not_found=False)
        if menu is None:
            self.skipTest("%s is not installed here" % xmlid.split(".")[0])
        return menu

    def test_the_group_carries_the_whole_merchant_set(self):
        implied = set(self.merchant_group.implied_ids.ids)
        for xmlid in MERCHANT_GROUPS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self.env.ref(xmlid).id, implied)

    def test_ticking_it_is_the_whole_gesture(self):
        for xmlid in MERCHANT_GROUPS:
            with self.subTest(xmlid=xmlid):
                self.assertTrue(self.merchant.has_group(xmlid))

    def test_the_dashboard_is_not_part_of_the_gesture(self):
        self.assertNotIn(self.dashboard_group, self.merchant_group.all_implied_ids)
        self.assertFalse(
            self.merchant.has_group("merchant_group.group_merchant_dashboard")
        )
        # A checkbox, not a selection: no privilege on either group.
        self.assertFalse(self.merchant_group.privilege_id)
        self.assertFalse(self.dashboard_group.privilege_id)

    def test_a_new_internal_user_is_a_merchant_by_default(self):
        """Core reads base.default_user_group.implied_ids in _default_groups."""
        self.assertIn(
            self.merchant_group, self.env.ref("base.default_user_group").implied_ids
        )
        user = self.env["res.users"].create(
            {"name": "Fresh Internal", "login": "merchant_group_fresh"}
        )
        self.assertTrue(user.has_group("merchant_group.group_merchant"))
        self.assertTrue(user.has_group("website.group_website_restricted_editor"))
        self.assertFalse(user.has_group("merchant_group.group_merchant_dashboard"))

    def test_a_hand_granted_permission_survives_the_group(self):
        """A group is not a role: nothing is recomposed on write."""
        extra = self.env.ref("base.group_partner_manager")
        user = self.env["res.users"].create(
            {
                "name": "Merchant With Extra",
                "login": "merchant_group_extra",
                "group_ids": [(4, self.merchant_group.id), (4, extra.id)],
            }
        )
        user.write({"name": "Merchant With Extra, renamed"})
        self.assertIn(extra, user.all_group_ids)

    def test_a_merchant_sees_the_profile_menus(self):
        visible = self._visible_ids(self.merchant)
        for xmlid in VISIBLE_ROOT_MENUS:
            with self.subTest(xmlid=xmlid):
                menu = self._menu(xmlid)
                self.assertFalse(menu.parent_id, "%s is not a root menu" % xmlid)
                self.assertIn(menu.id, visible)
        for xmlid in VISIBLE_INNER_MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self._menu(xmlid).id, visible)

    def test_a_merchant_does_not_see_the_rest(self):
        visible = self._visible_ids(self.merchant)
        for xmlid in HIDDEN_MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(self._menu(xmlid).id, visible)

    def test_the_gates_are_owned_in_replace_form(self):
        """A `-u crm` re-adds the salesman through Command.link; the gate
        written here must already be exactly what core intends."""
        salesman = self.env.ref("sales_team.group_sale_salesman")
        manager = self.env.ref("sales_team.group_sale_manager")
        self.assertEqual(
            self.env.ref("crm.crm_menu_root").group_ids, salesman | manager
        )
        self.assertEqual(
            self.env.ref(
                "spreadsheet_dashboard.spreadsheet_dashboard_menu_root"
            ).group_ids,
            self.env.ref("base.group_system"),
        )
        self.assertEqual(
            self.env.ref("sale_loyalty.menu_gift_ewallet_type_config").group_ids,
            manager,
        )

    def test_ticking_the_dashboard_shows_only_my_dashboard(self):
        self.merchant.write({"group_ids": [(4, self.dashboard_group.id)]})
        visible = self._visible_ids(self.merchant)
        mine = self.env.ref("merchant_group.menu_merchant_dashboard_root")
        self.assertIn(mine.id, visible)
        self.assertFalse(mine.parent_id)
        self.assertEqual(mine.action, self.env.ref("board.open_board_my_dash_action"))
        for xmlid in (
            "spreadsheet_dashboard.spreadsheet_dashboard_menu_root",
            "spreadsheet_dashboard.spreadsheet_dashboard_menu_dashboard",
            "board.menu_board_my_dash",
        ):
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(self._menu(xmlid).id, visible)

    def test_a_merchant_runs_the_loyalty_of_their_own_company_only(self):
        Program = self.env["loyalty.program"].with_user(self.merchant)
        program = Program.create(
            {
                "name": "Merchant Group Promotion",
                "program_type": "promotion",
                "company_id": self.company.id,
                "rule_ids": [(0, 0, {"minimum_amount": 10})],
                "reward_ids": [(0, 0, {"reward_type": "discount", "discount": 5})],
            }
        )
        self.assertEqual(program.company_id, self.company)
        program.write({"name": "Merchant Group Promotion, renamed"})
        self.assertIn(program.id, Program.search([]).ids)

        other = self.env["res.company"].search([("id", "!=", self.company.id)], limit=1)
        if not other:
            self.skipTest("a second company is needed")
        foreign = self.env["loyalty.program"].create(
            {
                "name": "Foreign Promotion",
                "program_type": "promotion",
                "company_id": other.id,
            }
        )
        self.assertNotIn(foreign.id, Program.search([]).ids)
        with self.assertRaises(AccessError):
            Program.browse(foreign.id).read(["name"])
        program.write({"active": False})
        program.unlink()
