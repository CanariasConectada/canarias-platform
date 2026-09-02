# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

from .common import create_taxonomy, make_test_image


@tagged("post_install", "-at_install")
class TestActivityAxis(HttpCase):
    """Two complementary taxonomies: what a place IS and what is DONE there.

    Asked for on 2026-09-02: "que se pudieran parametrizar las dos cosas,
    el tipo de lugar y las actividades [...] y dos selectores en el filtro".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_a, cls.category_a, cls.subcategory_a = create_taxonomy(cls.env, "Ax")
        cls.activity = cls.env["website.local.content.category"].create(
            {
                "name": "Test Outdoor Sports Ax",
                "type_id": cls.type_a.id,
                "axis": "activity",
            }
        )
        Item = cls.env["website.local.content.item"]
        cls.item_with_activity = Item.create(
            {
                "name": "WLC Sports Park Ax",
                "type_id": cls.type_a.id,
                "category_id": cls.category_a.id,
                "activity_category_ids": [(6, 0, cls.activity.ids)],
                "state": "approved",
                "is_published": True,
                "image_1920": make_test_image(),
            }
        )
        cls.item_without = Item.create(
            {
                "name": "WLC Quiet Beach Ax",
                "type_id": cls.type_a.id,
                "category_id": cls.category_a.id,
                "state": "approved",
                "is_published": True,
                "image_1920": make_test_image(),
            }
        )
        cls.index_url = "/explora/test-type-ax"

    def test_both_selectors_render_when_the_type_has_activities(self):
        # Markup, not wording: the page may render in any installed
        # language, item and category names are data and survive.
        html = self.url_open(self.index_url).text
        self.assertIn('name="category"', html)
        self.assertIn('name="activity"', html)
        self.assertIn("Test Outdoor Sports Ax", html)

    def test_the_activity_filter_narrows(self):
        html = self.url_open(
            f"{self.index_url}?activity={self.activity.id}"
        ).text
        self.assertIn("WLC Sports Park Ax", html)
        self.assertNotIn("WLC Quiet Beach Ax", html)

    def test_place_and_activity_filters_compose(self):
        """Both axes at once: the whole point of two selectors."""
        html = self.url_open(
            f"{self.index_url}/categoria/{self.category_a.id}"
            f"?activity={self.activity.id}"
        ).text
        self.assertIn("WLC Sports Park Ax", html)
        self.assertNotIn("WLC Quiet Beach Ax", html)

    def test_an_activity_never_appears_in_the_place_selector(self):
        html = self.url_open(self.index_url).text
        # The place select lists categories with counts; the activity name
        # must appear once (its own selector), not twice.
        self.assertEqual(html.count("Test Outdoor Sports Ax"), 1)

    def test_a_type_without_activities_keeps_a_single_selector(self):
        type_b, category_b, _sub = create_taxonomy(self.env, "Nx")
        self.env["website.local.content.item"].create(
            {
                "name": "WLC Memory Item Nx",
                "type_id": type_b.id,
                "category_id": category_b.id,
                "state": "approved",
                "is_published": True,
                "image_1920": make_test_image(),
            }
        )
        html = self.url_open("/explora/test-type-nx").text
        self.assertIn('name="category"', html)
        self.assertNotIn('name="activity"', html)

    def test_an_item_may_carry_only_activities(self):
        """The imported places arrived classified only by activity."""
        item = self.env["website.local.content.item"].create(
            {
                "name": "WLC Activity Only Ax",
                "type_id": self.type_a.id,
                "activity_category_ids": [(6, 0, self.activity.ids)],
                "state": "approved",
            }
        )
        self.assertFalse(item.category_id)
        self.assertEqual(item.activity_category_ids, self.activity)
