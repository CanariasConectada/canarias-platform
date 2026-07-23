# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase
from odoo.tests.common import new_test_user

from .common import create_taxonomy


class TestLocalContentTag(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_a, cls.category_a, cls.subcategory_a = create_taxonomy(cls.env, "A")
        cls.type_b, cls.category_b, cls.subcategory_b = create_taxonomy(cls.env, "B")
        cls.Item = cls.env["website.local.content.item"]
        cls.Tag = cls.env["website.local.content.tag"]
        cls.tag_transversal = cls.Tag.create({"name": "Heritage"})
        cls.tag_scoped = cls.Tag.create(
            {"name": "Gastronomy", "type_id": cls.type_a.id}
        )

    def _create_item(self, **extra):
        vals = {
            "name": "Casa del Niño",
            "type_id": self.type_a.id,
            "category_id": self.category_a.id,
        }
        vals.update(extra)
        return self.Item.create(vals)

    def test_tag_defaults(self):
        self.assertEqual(self.tag_transversal.sequence, 10)
        self.assertTrue(self.tag_transversal.active)
        self.assertFalse(self.tag_transversal.type_id)
        self.assertEqual(self.tag_scoped.type_id, self.type_a)

    def test_tag_ordering(self):
        first = self.Tag.create({"name": "ZZZ Last Name", "sequence": 1})
        tags = self.Tag.search([])
        self.assertEqual(tags[0], first)

    def test_item_tag_assignment(self):
        item = self._create_item(
            tag_ids=[(6, 0, (self.tag_transversal | self.tag_scoped).ids)]
        )
        self.assertEqual(len(item.tag_ids), 2)
        self.assertIn(self.tag_transversal, item.tag_ids)
        self.assertIn(self.tag_scoped, item.tag_ids)

    def test_tags_are_transversal_across_types(self):
        # A tag scoped to type A is still assignable to a type B item: the
        # type_id of the tag is informative scoping, never enforced.
        item_b = self._create_item(
            type_id=self.type_b.id,
            category_id=self.category_b.id,
            tag_ids=[(6, 0, (self.tag_transversal | self.tag_scoped).ids)],
        )
        self.assertEqual(len(item_b.tag_ids), 2)

    def test_tag_deletion_keeps_items(self):
        item = self._create_item(tag_ids=[(6, 0, self.tag_transversal.ids)])
        self.tag_transversal.unlink()
        self.assertFalse(item.tag_ids)
        self.assertTrue(item.exists())

    def test_visitor_can_read_tags(self):
        # Tags are rendered on the public detail page, so public and portal
        # users keep read access (same pattern as the category taxonomy).
        portal_user = new_test_user(
            self.env, login="wlc_tag_portal", groups="base.group_portal"
        )
        public_user = self.env.ref("base.public_user")
        for user in (public_user, portal_user):
            names = self.tag_transversal.with_user(user).read(["name"])
            self.assertEqual(names[0]["name"], "Heritage")
