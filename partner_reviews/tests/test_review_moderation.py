# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from psycopg2.errors import UniqueViolation

from odoo.exceptions import AccessError
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

    def _merchant_activities(self, moderator, company=None):
        company = company or self.company
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", company.partner_id.id),
                ("user_id", "=", moderator.id),
            ]
        )

    def test_pending_review_notifies_moderators(self):
        moderator = self._create_moderator("pr_moderator")
        self.env["review.forbidden.word"].create({"name": "swindle"})
        self._create_review(self.customer_1, 1, "swindle")
        # The activity lands on the merchant's partner because rating.rating
        # is not a mail.thread.
        self.assertTrue(
            self._merchant_activities(moderator),
            "Moderators must get a to-do activity",
        )

    def test_repeated_pending_edits_notify_once(self):
        """Re-saving forbidden feedback on an already-pending review must not
        create a second email/activity (DoS guard)."""
        moderator = self._create_moderator("pr_mod_once")
        self.env["review.forbidden.word"].create({"name": "swindle"})
        review = self._create_review(self.customer_1, 4, "Nice place")
        self.assertEqual(review.moderation_status, "approved")
        review.feedback = "a swindle for sure"
        self.assertEqual(review.moderation_status, "pending")
        review.feedback = "still a swindle honestly"
        self.assertEqual(review.moderation_status, "pending")
        self.assertEqual(
            len(self._merchant_activities(moderator)),
            1,
            "Editing an already-pending review must not pile up activities",
        )

    def test_moderator_of_other_company_is_not_notified(self):
        """A pending review of company A must not notify a moderator scoped to
        company B (cross-company isolation)."""
        company_b = self.env["res.company"].create(
            {"name": "PR Other Bakery", "enable_reviews": True}
        )
        mod_a = self._create_moderator("pr_mod_a", company=self.company)
        mod_b = self._create_moderator("pr_mod_b", company=company_b)
        self.env["review.forbidden.word"].create({"name": "swindle"})
        self._create_review(self.customer_1, 1, "swindle", company=self.company)
        self.assertTrue(
            self._merchant_activities(mod_a),
            "The company's own moderator must be notified",
        )
        self.assertFalse(
            self._merchant_activities(mod_b),
            "A moderator of another company must not be notified",
        )

    def test_internal_user_cannot_approve(self):
        """The native ACL lets any employee write rating.rating, but only
        moderators may flip the moderation status."""
        self.env["review.forbidden.word"].create({"name": "swindle"})
        review = self._create_review(self.customer_1, 1, "a swindle")
        self.assertEqual(review.moderation_status, "pending")
        internal = self.env["res.users"].create(
            {
                "name": "PR Employee",
                "login": "pr_employee",
                "email": "pr.employee@example.com",
                "company_id": self.company.id,
                "company_ids": [(6, 0, [self.company.id])],
                "group_ids": [(4, self.env.ref("base.group_user").id)],
            }
        )
        with self.assertRaises(AccessError):
            review.with_user(internal).write({"moderation_status": "approved"})
        self.assertEqual(review.moderation_status, "pending")

    def test_forbidden_word_matches_whole_word_only(self):
        """Word-boundary match: a forbidden word inside a legit word must not
        flag, the standalone word must."""
        self.env["review.forbidden.word"].create({"name": "cialis"})
        clean = self._create_review(self.customer_1, 5, "Un gran especialista")
        self.assertEqual(clean.moderation_status, "approved")
        flagged = self._create_review(self.customer_2, 1, "Vende cialis barato")
        self.assertEqual(flagged.moderation_status, "pending")

    @mute_logger("odoo.sql_db")
    def test_one_review_per_customer_and_company(self):
        self._create_review(self.customer_1, 4, "Good")
        with self.assertRaises(UniqueViolation), self.env.cr.savepoint():
            self._create_review(self.customer_1, 2, "Changed my mind")

    def _create_review_with_context(self, partner, rating, feedback="", **ctx):
        return (
            self.env["rating.rating"]
            .with_context(**ctx)
            .create(
                {
                    "res_model_id": self.company_model_id,
                    "res_id": self.company.id,
                    "partner_id": partner.id,
                    "rating": rating,
                    "feedback": feedback,
                    "consumed": True,
                }
            )
        )

    def test_skip_context_silences_merchant_email(self):
        """skip_review_notifications must prevent the merchant mail.mail:
        bulk flows (data migration) import historical reviews silently."""
        self.company.email = "pr.merchant@example.com"
        mails_before = self.env["mail.mail"].sudo().search_count([])
        review = self._create_review_with_context(
            self.customer_1, 5, "Historic review",
            skip_review_notifications=True,
        )
        self.assertEqual(review.moderation_status, "approved")
        self.assertEqual(
            self.env["mail.mail"].sudo().search_count([]),
            mails_before,
            "No mail.mail may be created under skip_review_notifications",
        )

    def test_skip_context_silences_moderator_notifications(self):
        """A pending (forbidden-word) review created under the skip context
        must raise neither the moderator email nor the to-do activity."""
        moderator = self._create_moderator("pr_mod_skip")
        self.env["review.forbidden.word"].create({"name": "swindle"})
        mails_before = self.env["mail.mail"].sudo().search_count([])
        review = self._create_review_with_context(
            self.customer_1, 1, "a swindle",
            skip_review_notifications=True,
        )
        self.assertEqual(review.moderation_status, "pending")
        self.assertEqual(
            self.env["mail.mail"].sudo().search_count([]), mails_before
        )
        self.assertFalse(
            self._merchant_activities(moderator),
            "No moderation activity may be created under the skip context",
        )

    @mute_logger("odoo.addons.mail.models.mail_mail")
    def test_merchant_email_still_sent_without_skip_context(self):
        """Control: without the context the merchant mail.mail IS created
        (proves the skip tests are not vacuously green)."""
        self.company.email = "pr.merchant@example.com"
        mails_before = self.env["mail.mail"].sudo().search_count([])
        self._create_review(self.customer_2, 4, "Great bakery")
        self.assertEqual(
            self.env["mail.mail"].sudo().search_count([]), mails_before + 1
        )

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
