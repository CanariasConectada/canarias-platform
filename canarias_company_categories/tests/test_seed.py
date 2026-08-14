# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.canarias_company_categories.hooks import (
    DEFAULT_CATEGORIES,
    post_init_hook,
)


@tagged("post_install", "-at_install")
class TestCanariasCompanyCategories(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env["res.company.category"]

    def test_taxonomy_seeded(self):
        roots = self.Category.search([("parent_id", "=", False)])
        expected_roots = {name for name, parent in DEFAULT_CATEGORIES if not parent}
        self.assertTrue(expected_roots.issubset(set(roots.mapped("name"))))

    def test_roots_are_view_leaves_are_normal(self):
        alimentacion = self.Category.search(
            [("name", "=", "Alimentación"), ("parent_id", "=", False)]
        )
        self.assertEqual(alimentacion.type, "view")
        bar = self.Category.search([("name", "=", "Bar")])
        self.assertEqual(len(bar), 1)
        self.assertEqual(bar.type, "normal")
        self.assertEqual(bar.parent_id.name, "Restauración/Ocio")
        self.assertEqual(bar.complete_name, "Restauración/Ocio / Bar")

    def test_seed_is_idempotent(self):
        count_before = self.Category.search_count([])
        post_init_hook(self.env)
        self.assertEqual(self.Category.search_count([]), count_before)

    def test_company_assignment_and_qty(self):
        farmacia = self.Category.search([("name", "=", "Farmacia")])
        company = self.env["res.company"].create(
            {"name": "CCC Test Co", "category_id": farmacia.id}
        )
        self.assertIn(company, farmacia.company_ids)
        self.assertEqual(farmacia.company_qty, 1)
        # The "view" parent aggregates its children quantities.
        self.assertEqual(farmacia.parent_id.company_qty, 1)
