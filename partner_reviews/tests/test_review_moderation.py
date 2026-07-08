# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from psycopg2.errors import UniqueViolation

from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import PartnerReviewsCase


@tagged("post_install", "-at_install")
class TestReviewModeration(PartnerReviewsCase):
    def test_clean_review_is_auto_approved(self):
        review = self._create_review(self.customer_1, 5, "Excellent service")
        self.assertEqual(review.moderation_status, "approved")
        self.assertFalse(review.requires_moderation)

    def test_forbidden_word_holds_review(self):
        self.env["review.forbidden.word"].create({"name": "swindle"})
        review = self._create_review(self.customer_1, 1, "A total SWINDLE!")
        self.assertEqual(review.moderation_status, "pending")
        self.assertTrue(review.requires_moderation)

    def test_archived_word_is_ignored(self):
        self.env["review.forbidden.word"].create({"name": "meh", "active": False})
        review = self._create_review(self.customer_1, 3, "It was meh.")
        self.assertEqual(review.moderation_status, "approved")

    def test_editing_feedback_reapplies_moderation(self):
        self.env["review.forbidden.word"].create({"name": "swindle"})
        review = self._create_review(self.customer_1, 4, "Nice place")
        self.assertEqual(review.moderation_status, "approved")
        review.feedback = "Actually a swindle"
        self.assertEqual(review.moderation_status, "pending")

    def test_approve_and_reject_actions(self):
        self.env["review.forbidden.word"].create({"name": "swindle"})
        review = self._create_review(self.customer_1, 1, "swindle")
        review.action_approve()
        self.assertEqual(review.moderation_status, "approved")
        review.action_reject()
        self.assertEqual(review.moderation_status, "rejected")

    def test_pending_review_notifies_moderators(self):
        moderator = self.env["res.users"].create(
            {
                "name": "PR Moderator",
                "login": "pr_moderator",
                "email": "pr.moderator@example.com",
                "group_ids": [
                    (
                        4,
                        self.env.ref(
                            "partner_reviews.group_partner_reviews_moderator"
                        ).id,
                    )
                ],
            }
        )
        self.env["review.forbidden.word"].create({"name": "swindle"})
        self._create_review(self.customer_1, 1, "swindle")
        # The activity lands on the merchant's partner because rating.rating
        # is not a mail.thread.
        activity = self.env["mail.activity"].search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", self.company.partner_id.id),
                ("user_id", "=", moderator.id),
            ]
        )
        self.assertTrue(activity, "Moderators must get a to-do activity")

    @mute_logger("odoo.sql_db")
    def test_one_review_per_customer_and_company(self):
        self._create_review(self.customer_1, 4, "Good")
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_review(self.customer_1, 2, "Changed my mind")

    def test_non_merchant_ratings_untouched(self):
        """Ratings of other apps must keep the default approved status and
        never enter the merchant moderation flow."""
        self.env["review.forbidden.word"].create({"name": "swindle"})
        rating = self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.customer_2.id,
                "partner_id": self.customer_1.id,
                "rating": 2,
                "feedback": "swindle",
                "consumed": True,
            }
        )
        self.assertEqual(rating.moderation_status, "approved")
        self.assertFalse(rating.requires_moderation)
