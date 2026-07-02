# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

SAMPLE = """
  BCHW Food
Bakery
[Fruit Shop](https://example.com/ignored)
  BCHW Services
Plumber
"""


@tagged("post_install", "-at_install")
class TestImportWizard(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Category = cls.env["business.category"]
        cls.Wizard = cls.env["business.category.import"]

    def _run(self, data):
        wizard = self.Wizard.create({"import_data": data})
        return wizard.action_import()

    def test_import_creates_hierarchy(self):
        action = self._run(SAMPLE)
        food = self.Category.search(
            [("name", "=", "BCHW Food"), ("parent_id", "=", False)]
        )
        self.assertEqual(len(food), 1)
        self.assertEqual(set(food.child_ids.mapped("name")), {"Bakery", "Fruit Shop"})
        services = self.Category.search([("name", "=", "BCHW Services")])
        self.assertEqual(services.child_ids.mapped("name"), ["Plumber"])
        created_ids = action["domain"][0][2]
        self.assertEqual(len(created_ids), 5)

    def test_import_is_idempotent(self):
        self._run(SAMPLE)
        action = self._run(SAMPLE)
        self.assertEqual(action["domain"][0][2], [])
        self.assertEqual(self.Category.search_count([("name", "=", "BCHW Food")]), 1)

    def test_markdown_url_is_ignored(self):
        self._run(SAMPLE)
        fruit = self.Category.search([("name", "=", "Fruit Shop")])
        self.assertEqual(len(fruit), 1)
        self.assertNotIn("example.com", fruit.complete_name)

    def test_orphan_child_becomes_root(self):
        self._run("Standalone BCHW")
        record = self.Category.search([("name", "=", "Standalone BCHW")])
        self.assertEqual(len(record), 1)
        self.assertFalse(record.parent_id)
