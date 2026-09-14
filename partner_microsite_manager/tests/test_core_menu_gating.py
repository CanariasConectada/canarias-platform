# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCoreMenuGating(TransactionCase):
    """Menus a merchant has no business opening are closed for good.

    Writing ``group_ids`` on an existing menu REPLACES its gate; a menuitem's
    ``groups`` attribute would only add one. Both menus below ship with no
    gate at all, which is why every internal user could see them.
    """

    GATED = ["base.menu_management", "spreadsheet_dashboard.spreadsheet_dashboard_menu_root"]

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.merchant = cls.env["res.users"].create(
            {
                "name": "Core Gating Merchant",
                "login": "core_gating_merchant",
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("website.group_website_restricted_editor").id),
                ],
            }
        )
        cls.staff = cls.env["res.users"].create(
            {
                "name": "Core Gating Staff",
                "login": "core_gating_staff",
                "group_ids": [
                    (4, cls.env.ref("base.group_user").id),
                    (4, cls.env.ref("base.group_system").id),
                ],
            }
        )

    def _visible(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_a_merchant_is_not_offered_apps_or_dashboards(self):
        visible = self._visible(self.merchant)
        for xmlid in self.GATED:
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, visible)

    def test_platform_staff_keeps_them(self):
        visible = self._visible(self.staff)
        for xmlid in self.GATED:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self.env.ref(xmlid).id, visible)
