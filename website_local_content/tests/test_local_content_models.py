# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import date

from psycopg2.errors import UniqueViolation

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase
from odoo.tools import mute_logger

from .common import create_taxonomy, make_test_image


class TestLocalContentModels(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_a, cls.category_a, cls.subcategory_a = create_taxonomy(cls.env, "A")
        cls.type_b, cls.category_b, cls.subcategory_b = create_taxonomy(cls.env, "B")
        cls.Item = cls.env["website.local.content.item"]

    def _create_item(self, **extra):
        vals = {
            "name": "Casa del Niño",
            "type_id": self.type_a.id,
            "category_id": self.category_a.id,
        }
        vals.update(extra)
        return self.Item.create(vals)

    def test_slug_autogeneration_and_dedup(self):
        item_1 = self._create_item()
        self.assertEqual(item_1.slug, "casa-del-nino")
        item_2 = self._create_item()
        self.assertEqual(item_2.slug, "casa-del-nino-1")

    def test_same_slug_allowed_across_types(self):
        item_a = self._create_item()
        item_b = self._create_item(
            type_id=self.type_b.id, category_id=self.category_b.id
        )
        self.assertEqual(item_a.slug, item_b.slug)

    @mute_logger("odoo.sql_db")
    def test_slug_unique_within_type(self):
        self._create_item()
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_item(slug="casa-del-nino")

    def test_photo_year_bounds(self):
        item = self._create_item(photo_year=1965)
        self.assertEqual(item.decade, 1960)
        with self.assertRaises(ValidationError):
            self._create_item(photo_year=1700)
        with self.assertRaises(ValidationError):
            self._create_item(photo_year=date.today().year + 1)

    def test_decade_recomputed_on_write(self):
        item = self._create_item(photo_year=1965)
        item.photo_year = 1971
        self.assertEqual(item.decade, 1970)
        item.photo_year = False
        self.assertEqual(item.decade, 0)

    def test_coordinates_bounds(self):
        with self.assertRaises(ValidationError):
            self._create_item(latitude=120.0)
        with self.assertRaises(ValidationError):
            self._create_item(longitude=200.0)

    def test_taxonomy_consistency(self):
        with self.assertRaises(ValidationError):
            self._create_item(category_id=self.category_b.id)
        with self.assertRaises(ValidationError):
            self._create_item(subcategory_id=self.subcategory_b.id)

    def test_workflow_actions(self):
        item = self._create_item()
        self.assertEqual(item.state, "draft")
        item.action_submit_for_approval()
        self.assertEqual(item.state, "pending")
        item.action_approve()
        self.assertEqual(item.state, "approved")
        self.assertTrue(item.is_published)
        item.action_reject()
        self.assertEqual(item.state, "rejected")
        self.assertFalse(item.is_published)

    def test_website_url(self):
        item = self._create_item()
        self.assertEqual(item.website_url, f"/explora/test-type-a/{item.slug}")

    def test_like_count_and_session_check(self):
        item = self._create_item()
        like_model = self.env["website.local.content.like"]
        like_model.create({"item_id": item.id, "session_key": "session-1"})
        like_model.create({"item_id": item.id, "session_key": "session-2"})
        self.assertEqual(item.like_count, 2)
        self.assertTrue(item.has_session_liked("session-1"))
        self.assertFalse(item.has_session_liked("session-3"))

    @mute_logger("odoo.sql_db")
    def test_like_unique_per_session(self):
        item = self._create_item()
        like_model = self.env["website.local.content.like"]
        like_model.create({"item_id": item.id, "session_key": "session-1"})
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            like_model.create({"item_id": item.id, "session_key": "session-1"})

    def test_type_url_slug_validation(self):
        with self.assertRaises(ValidationError):
            self.env["website.local.content.type"].create(
                {"name": "Bad", "code": "bad", "url_slug": "Not A Slug!"}
            )

    def test_image_mixin_resizes(self):
        item = self._create_item(image_1920=make_test_image())
        self.assertTrue(item.image_128)

    def test_website_visibility(self):
        website_a = self.env["website"].create({"name": "WLC Site A"})
        website_b = self.env["website"].create({"name": "WLC Site B"})
        everywhere = self._create_item(state="approved", is_published=True)
        only_a = self._create_item(
            state="approved",
            is_published=True,
            website_ids=[(6, 0, website_a.ids)],
        )
        # Empty website_ids means visible on every website.
        self.assertTrue(everywhere._is_visible_on_website(website_a))
        self.assertTrue(everywhere._is_visible_on_website(website_b))
        # A scoped item is only visible on its own website(s).
        self.assertTrue(only_a._is_visible_on_website(website_a))
        self.assertFalse(only_a._is_visible_on_website(website_b))
        # The search domain matches the per-record helper.
        domain_b = self.Item._get_website_visibility_domain(website_b)
        visible_on_b = self.Item.search(domain_b)
        self.assertIn(everywhere, visible_on_b)
        self.assertNotIn(only_a, visible_on_b)
