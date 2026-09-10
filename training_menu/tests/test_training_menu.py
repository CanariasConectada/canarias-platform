# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTrainingMenu(TransactionCase):
    def test_every_internal_user_sees_formacion_and_it_opens_the_courses(self):
        user = self.env["res.users"].create(
            {
                "name": "Training Menu Clerk",
                "login": "training_menu_clerk",
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        menu = self.env.ref("training_menu.menu_training_root")
        self.assertIn(menu.id, self.env["ir.ui.menu"].with_user(user)._visible_menu_ids())
        self.assertFalse(menu.parent_id, "a root entry, next to the apps")
        action = self.env.ref("training_menu.action_training_courses")
        self.assertEqual(action.url, "https://canariasconectada.es/slides")
        self.assertEqual(action.target, "new")

    def test_the_entry_is_for_internal_users_only(self):
        """Gated on base.group_user: a portal account never carries it."""
        menu = self.env.ref("training_menu.menu_training_root")
        self.assertEqual(menu.group_ids, self.env.ref("base.group_user"))
