# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestTwinCategories(TransactionCase):
    """Same visible name, one sidebar entry, one filter that means all of it.

    Reported on 2026-09-02: "Hay categorias de producto repetidas. En algunos
    casos aparecen 5 o 6 veces la misma categoria" -- migration debris, one
    copy of the everyday names per merchant.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env["product.public.category"]
        cls.entrantes_a = Category.create({"name": "Entrantes"})
        cls.entrantes_b = Category.create({"name": "entrantes "})
        cls.postres = Category.create({"name": "Postres"})
        # A subcategory sharing a top-level name must NOT be merged with it.
        cls.entrantes_child = Category.create(
            {"name": "Entrantes", "parent_id": cls.postres.id}
        )

    def test_twins_are_found_case_and_space_insensitively(self):
        twins = self.entrantes_a._shop_twin_categories()
        self.assertIn(self.entrantes_a, twins)
        self.assertIn(self.entrantes_b, twins)
        self.assertNotIn(self.postres, twins)

    def test_a_subcategory_is_not_a_twin_of_a_top_level_one(self):
        self.assertNotIn(
            self.entrantes_child, self.entrantes_a._shop_twin_categories()
        )
        self.assertEqual(
            self.entrantes_child._shop_twin_categories(), self.entrantes_child
        )

    def test_a_lonely_category_is_its_own_twin_set(self):
        self.assertEqual(self.postres._shop_twin_categories(), self.postres)

    def test_a_wildcard_in_the_name_stays_a_letter(self):
        """Merchant data must never widen into an SQL pattern."""
        Category = self.env["product.public.category"]
        wild = Category.create({"name": "100% Canario"})
        decoy = Category.create({"name": "100x Canario"})
        self.assertNotIn(decoy, wild._shop_twin_categories())
