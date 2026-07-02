# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.business_category_hierarchy.hooks import (
    DEFAULT_CATEGORIES,
    post_init_hook,
)


@tagged("post_install", "-at_install")
class TestBusinessCategory(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env["business.category"]
        cls.root = cls.Category.create({"name": "BCH Root"})
        cls.child = cls.Category.create({"name": "BCH Child", "parent_id": cls.root.id})
        cls.grandchild = cls.Category.create(
            {"name": "BCH Grandchild", "parent_id": cls.child.id}
        )

    def test_complete_name(self):
        self.assertEqual(self.root.complete_name, "BCH Root")
        self.assertEqual(self.child.complete_name, "BCH Root / BCH Child")
        self.assertEqual(
            self.grandchild.complete_name, "BCH Root / BCH Child / BCH Grandchild"
        )

    def test_complete_name_follows_parent_rename(self):
        self.root.name = "BCH Renamed"
        self.assertEqual(
            self.grandchild.complete_name, "BCH Renamed / BCH Child / BCH Grandchild"
        )
        self.assertIn("BCH Renamed", self.grandchild.display_name)

    def test_hierarchy_level(self):
        self.assertEqual(self.root.hierarchy_level, 1)
        self.assertEqual(self.child.hierarchy_level, 2)
        self.assertEqual(self.grandchild.hierarchy_level, 3)

    def test_hierarchy_level_follows_reparent(self):
        self.grandchild.parent_id = self.root
        self.assertEqual(self.grandchild.hierarchy_level, 2)

    def test_recursion_forbidden(self):
        # _parent_store detects the cycle first (UserError "Recursion
        # Detected."); the constraint (ValidationError, a UserError
        # subclass) is kept for parity with core product.category.
        with self.assertRaises(UserError):
            self.root.parent_id = self.grandchild

    def test_name_create(self):
        record_id, display_name = self.Category.name_create("BCH Quick")
        record = self.Category.browse(record_id)
        self.assertEqual(record.name, "BCH Quick")
        self.assertEqual(display_name, "BCH Quick")
        self.assertFalse(record.parent_id)

    def test_company_assignment(self):
        company = self.env["res.company"].create({"name": "BCH Test Co"})
        company.business_category_ids = self.child
        self.assertEqual(self.child.company_ids, company)
        self.assertEqual(self.child.company_count, 1)
        self.assertEqual(self.root.company_count, 0)

    def test_seed_taxonomy_installed(self):
        roots = self.Category.search([("parent_id", "=", False)])
        expected_roots = {name for name, parent in DEFAULT_CATEGORIES if not parent}
        self.assertTrue(expected_roots.issubset(set(roots.mapped("name"))))

    def test_seed_hook_is_idempotent(self):
        count_before = self.Category.search_count([])
        post_init_hook(self.env)
        self.assertEqual(self.Category.search_count([]), count_before)

    def test_archived_not_in_default_search(self):
        self.grandchild.active = False
        self.assertNotIn(
            self.grandchild, self.Category.search([("name", "like", "BCH")])
        )
