# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase

from .common import create_taxonomy


class TestLocalContentRating(TransactionCase):
    """Read-only display of the migrated legacy ratings on public pages."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_a, cls.category_a, _sub = create_taxonomy(cls.env, "R")
        cls.item = cls.env["website.local.content.item"].create(
            {
                "name": "Rated Place",
                "type_id": cls.type_a.id,
                "category_id": cls.category_a.id,
            }
        )
        cls.item.action_approve()
        cls.partner = cls.env["res.partner"].create({"name": "Reviewer Ana"})
        cls.item_model_id = cls.env["ir.model"]._get_id("website.local.content.item")

    def _create_rating(self, rate, partner=None, consumed=True, item=None, **extra):
        vals = {
            "res_model_id": self.item_model_id,
            "res_id": (item or self.item).id,
            "rating": rate,
            "consumed": consumed,
            "partner_id": partner.id if partner else False,
        }
        vals.update(extra)
        return self.env["rating.rating"].create(vals)

    def test_rating_stats_average_and_count(self):
        for rate in (5, 4, 3):
            self._create_rating(rate)
        self.assertEqual(self.item.rating_count, 3)
        self.assertAlmostEqual(self.item.rating_avg, 4.0, places=2)

    def test_rating_stats_ignore_unconsumed_and_empty(self):
        self._create_rating(5)
        # An unfilled (not consumed) request and a zero-valued row must not
        # count, exactly as in ``rating.mixin._rating_domain``.
        self._create_rating(1, consumed=False)
        self._create_rating(0)
        self.assertEqual(self.item.rating_count, 1)
        self.assertAlmostEqual(self.item.rating_avg, 5.0, places=2)

    def test_item_without_ratings_shows_nothing(self):
        self.assertEqual(self.item.rating_count, 0)
        self.assertAlmostEqual(self.item.rating_avg, 0.0, places=2)
        self.assertFalse(self.item.get_public_ratings())

    def test_public_ratings_newest_first_and_feedback(self):
        old = self._create_rating(3, feedback="Old memory")
        new = self._create_rating(5, feedback="Beautiful place")
        reviews = self.item.get_public_ratings()
        self.assertEqual(reviews.ids, [new.id, old.id])
        self.assertEqual(reviews[0].feedback, "Beautiful place")

    def test_rating_author_name_visitor_fallback(self):
        # The fallback resolves against the ambient language, Spanish on
        # this database since the language rollout. Pinned to keep the
        # expectation literal.
        self.env.user.lang = "en_US"
        anonymous = self._create_rating(4)
        named = self._create_rating(5, partner=self.partner)
        item_model = self.env["website.local.content.item"]
        self.assertEqual(item_model.get_rating_author_name(anonymous), "Visitor")
        self.assertEqual(item_model.get_rating_author_name(named), "Reviewer Ana")

    def test_unpublished_item_hides_public_ratings(self):
        self._create_rating(5)
        self.assertTrue(self.item.get_public_ratings())
        self.item.action_reset_to_draft()
        self.assertFalse(self.item.get_public_ratings())
        # Approved but manually unpublished: still nothing public.
        self.item.write({"state": "approved", "is_published": False})
        self.assertFalse(self.item.get_public_ratings())

    def test_rating_stats_are_per_item(self):
        other = self.env["website.local.content.item"].create(
            {
                "name": "Other Place",
                "type_id": self.type_a.id,
                "category_id": self.category_a.id,
            }
        )
        other.action_approve()
        self._create_rating(5)
        self._create_rating(1, item=other)
        self.assertAlmostEqual(self.item.rating_avg, 5.0, places=2)
        self.assertAlmostEqual(other.rating_avg, 1.0, places=2)
        self.assertEqual((self.item + other).mapped("rating_count"), [1, 1])
