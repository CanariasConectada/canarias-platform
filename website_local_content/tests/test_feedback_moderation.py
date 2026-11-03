# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

from .common import create_taxonomy, make_test_image

CSRF_PATTERN = re.compile(r'name="csrf_token" value="([^"]+)"')


class FeedbackModerationMixin:
    """Helpers shared by the model and HTTP suites."""

    @classmethod
    def _add_word(cls, name, active=True):
        """A forbidden word of the shared list, created or reused (the seed
        is unique on the accent-folded form, so a blind create may
        collide with it)."""
        Word = cls.env["moderation.forbidden.word"].with_context(active_test=False)
        word = Word.search([("name_normalized", "=", Word._normalize(name))], limit=1)
        if word:
            word.active = active
            return word
        return Word.create({"name": name, "active": active})

    @classmethod
    def _make_item(cls, suffix):
        content_type, category, _sub = create_taxonomy(cls.env, suffix)
        item = cls.env["website.local.content.item"].create(
            {
                "name": f"WLC Moderated Place {suffix}",
                "type_id": content_type.id,
                "category_id": category.id,
                "state": "approved",
                "is_published": True,
                "image_1920": make_test_image(),
            }
        )
        return content_type, item

    def _rating(self, partner, stars, feedback="", item=None, **ctx):
        return (
            self.env["rating.rating"]
            .with_context(**ctx)
            .create(
                {
                    "res_model_id": self.env["ir.model"]._get_id(self.item._name),
                    "res_id": (item or self.item).id,
                    "partner_id": partner.id,
                    "rating": stars,
                    "feedback": feedback,
                    "consumed": True,
                }
            )
        )


@tagged("post_install", "-at_install")
class TestFeedbackModeration(FeedbackModerationMixin, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.content_type, cls.item = cls._make_item("FM")
        cls.author = cls.env["res.partner"].create({"name": "WLC Author"})
        cls.other = cls.env["res.partner"].create({"name": "WLC Other Author"})
        cls._add_word("swindle")
        cls._add_word("imbécil")
        cls._add_word("hijo de puta")

    def _create_manager(self, login):
        return new_test_user(
            self.env,
            login=login,
            groups="base.group_user,website_local_content.group_local_content_manager",
        )

    def _author_activities(self, user, author=None):
        return self.env["mail.activity"].search(
            [
                ("res_model", "=", "res.partner"),
                ("res_id", "=", (author or self.author).id),
                ("user_id", "=", user.id),
            ]
        )

    # --- Hit / clean ---------------------------------------------------------
    def test_clean_comment_is_published(self):
        rating = self._rating(self.author, 5, "Lovely place")
        self.assertEqual(rating.feedback_moderation_status, "approved")

    def test_empty_comment_is_published(self):
        rating = self._rating(self.author, 3, "")
        self.assertEqual(rating.feedback_moderation_status, "approved")

    def test_forbidden_word_holds_comment_but_stars_count(self):
        rating = self._rating(self.author, 1, "A total SWINDLE")
        self.assertEqual(rating.feedback_moderation_status, "pending")
        self.assertEqual(rating.rating, 1)
        # The stars are published at once: they count in the item stats
        # and the rating is part of the public list (its text is what the
        # template hides).
        self.env.invalidate_all()
        self.assertEqual(self.item.rating_count, 1)
        self.assertAlmostEqual(self.item.rating_avg, 1.0, places=2)
        self.assertIn(rating, self.item.get_public_ratings())

    def test_folding_case_and_accents(self):
        for index, text in enumerate(("IMBÉCIL", "imbecil", "Imbécil")):
            partner = self.env["res.partner"].create({"name": f"WLC Fold {index}"})
            rating = self._rating(partner, 2, text)
            self.assertEqual(rating.feedback_moderation_status, "pending", text)
        clean = self._rating(self.author, 4, "Sin imbecilidad, todo perfecto")
        self.assertEqual(clean.feedback_moderation_status, "approved")

    def test_multi_word_entry(self):
        rating = self._rating(self.author, 1, "Eres un hijo   de\nPUTA")
        self.assertEqual(rating.feedback_moderation_status, "pending")

    def test_archived_word_is_ignored(self):
        self._add_word("meh", active=False)
        rating = self._rating(self.author, 3, "It was meh")
        self.assertEqual(rating.feedback_moderation_status, "approved")

    def test_non_local_content_ratings_untouched(self):
        rating = self.env["rating.rating"].create(
            {
                "res_model_id": self.env["ir.model"]._get_id("res.partner"),
                "res_id": self.other.id,
                "partner_id": self.author.id,
                "rating": 2,
                "feedback": "swindle",
                "consumed": True,
            }
        )
        self.assertEqual(rating.feedback_moderation_status, "approved")

    # --- Editing ---------------------------------------------------------------
    def test_editing_held_comment_reevaluates(self):
        rating = self._rating(self.author, 2, "swindle")
        self.assertEqual(rating.feedback_moderation_status, "pending")
        rating.write({"feedback": "Actually fine", "rating": 4})
        self.assertEqual(rating.feedback_moderation_status, "approved")
        rating.write({"feedback": "No, a swindle"})
        self.assertEqual(rating.feedback_moderation_status, "pending")

    def test_same_comment_resaved_keeps_manager_decision(self):
        """The public form re-posts stars and comment together: an approved
        comment saved again with new stars must stay approved."""
        rating = self._rating(self.author, 2, "swindle")
        rating.action_approve_feedback()
        rating.write({"rating": 5, "feedback": "swindle"})
        self.assertEqual(rating.feedback_moderation_status, "approved")

    def test_rejected_comment_reevaluated_on_new_text(self):
        rating = self._rating(self.author, 2, "swindle")
        rating.action_reject_feedback()
        self.assertEqual(rating.feedback_moderation_status, "rejected")
        rating.write({"rating": 3, "feedback": "swindle"})
        self.assertEqual(rating.feedback_moderation_status, "rejected")
        rating.write({"feedback": "Sorry, great place"})
        self.assertEqual(rating.feedback_moderation_status, "approved")

    # --- Manager actions and access -------------------------------------------
    def test_approve_and_reject_actions(self):
        rating = self._rating(self.author, 1, "swindle")
        manager = self._create_manager("wlc_fm_manager")
        rating.with_user(manager).action_approve_feedback()
        self.assertEqual(rating.feedback_moderation_status, "approved")
        rating.with_user(manager).action_reject_feedback()
        self.assertEqual(rating.feedback_moderation_status, "rejected")

    def test_internal_user_cannot_change_status(self):
        rating = self._rating(self.author, 1, "swindle")
        employee = new_test_user(self.env, login="wlc_fm_employee")
        with self.assertRaises(AccessError):
            rating.with_user(employee).write({"feedback_moderation_status": "approved"})
        self.assertEqual(rating.feedback_moderation_status, "pending")

    # --- Notifications ---------------------------------------------------------
    def test_pending_comment_notifies_managers_once(self):
        manager = self._create_manager("wlc_fm_notified")
        rating = self._rating(self.author, 1, "swindle")
        self.assertEqual(len(self._author_activities(manager)), 1)
        # Re-saving forbidden text on an already pending comment must not
        # pile up activities (DoS guard).
        rating.write({"feedback": "still a swindle"})
        self.assertEqual(rating.feedback_moderation_status, "pending")
        self.assertEqual(len(self._author_activities(manager)), 1)

    def test_no_manager_falls_back_to_admins(self):
        group = self.env.ref("website_local_content.group_local_content_manager")
        group.write({"user_ids": [(5, 0, 0)]})
        self.assertFalse(group.all_user_ids)
        admin = self.env.ref("base.user_admin")
        self._rating(self.author, 1, "swindle")
        self.assertTrue(self._author_activities(admin))

    def test_activities_closed_on_decision_and_delete(self):
        manager = self._create_manager("wlc_fm_closer")
        first = self._rating(self.author, 1, "swindle")
        self.assertEqual(len(self._author_activities(manager)), 1)
        first.action_approve_feedback()
        self.assertFalse(self._author_activities(manager), "approve closes the to-do")

        second = self._rating(self.other, 1, "swindle")
        self.assertEqual(len(self._author_activities(manager, self.other)), 1)
        second.unlink()
        self.assertFalse(
            self._author_activities(manager, self.other), "delete closes the to-do"
        )

    def test_activity_kept_while_another_comment_is_held(self):
        manager = self._create_manager("wlc_fm_keeper")
        _type, other_item = self._make_item("FK")
        held_a = self._rating(self.author, 1, "swindle")
        self._rating(self.author, 2, "swindle here too", item=other_item)
        self.assertEqual(len(self._author_activities(manager)), 1)
        held_a.action_reject_feedback()
        self.assertEqual(len(self._author_activities(manager)), 1, "one still held")

    def test_batch_create_moderates_each_rating(self):
        partners = self.env["res.partner"].create(
            [{"name": "WLC Batch %s" % index} for index in range(3)]
        )
        ratings = self.env["rating.rating"].create(
            [
                {
                    "res_model_id": self.env["ir.model"]._get_id(self.item._name),
                    "res_id": self.item.id,
                    "partner_id": partner.id,
                    "rating": 4,
                    "feedback": feedback,
                    "consumed": True,
                }
                for partner, feedback in zip(
                    partners, ("a SWINDLE", "all good", "IMBÉCIL")
                )
            ]
        )
        self.assertEqual(
            ratings.mapped("feedback_moderation_status"),
            ["pending", "approved", "pending"],
        )
        self.env.invalidate_all()
        self.assertEqual(self.item.rating_count, 3)

    def test_held_comment_hidden_from_plain_internal_users(self):
        """Core grants every employee read on rating.rating; the global rule
        keeps held and rejected local content comments for managers, admins
        and their author."""
        held = self._rating(self.author, 1, "swindle")
        clean = self._rating(self.other, 5, "Lovely")
        employee = new_test_user(self.env, login="wlc_fm_reader")
        Rating = self.env["rating.rating"].with_user(employee)
        domain = [("res_model", "=", self.item._name), ("res_id", "=", self.item.id)]
        self.assertEqual(Rating.search(domain), clean)
        with self.assertRaises(AccessError):
            Rating.browse(held.id).read(["feedback"])
        held.action_reject_feedback()
        self.assertEqual(Rating.search(domain), clean)
        manager = self._create_manager("wlc_fm_reader_mgr")
        self.assertEqual(
            self.env["rating.rating"].with_user(manager).search(domain), held | clean
        )
        # The author (an internal user here) reads their own held row.
        author_user = new_test_user(self.env, login="wlc_fm_reader_author")
        own = self._rating(author_user.partner_id, 2, "swindle")
        self.assertIn(
            own, self.env["rating.rating"].with_user(author_user).search(domain)
        )

    def test_skip_context_silences_notifications(self):
        manager = self._create_manager("wlc_fm_silent")
        mails_before = self.env["mail.mail"].sudo().search_count([])
        rating = self._rating(self.author, 1, "swindle", skip_review_notifications=True)
        self.assertEqual(rating.feedback_moderation_status, "pending")
        self.assertFalse(self._author_activities(manager))
        self.assertEqual(self.env["mail.mail"].sudo().search_count([]), mails_before)


@tagged("post_install", "-at_install")
class TestFeedbackModerationWebsite(FeedbackModerationMixin, HttpCase):
    """The public detail page: held text visible to its author only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.content_type, cls.item = cls._make_item("FW")
        cls.detail_url = cls.item.website_url
        cls.rate_url = f"/explora/{cls.content_type.url_slug}/rate/{cls.item.id}"
        cls.author_user = new_test_user(
            cls.env, login="wlc_fm_author", groups="base.group_portal"
        )
        cls.other_user = new_test_user(
            cls.env, login="wlc_fm_other", groups="base.group_portal"
        )
        cls._add_word("swindle")

    def setUp(self):
        super().setUp()
        website = self.env["website"].search([], limit=1)
        self.opener.cookies["frontend_lang"] = website.default_lang_id.code

    def _page(self):
        response = self.url_open(self.detail_url)
        self.assertEqual(response.status_code, 200)
        return response.text

    def _rate(self, **data):
        csrf = CSRF_PATTERN.search(self._page()).group(1)
        return self.url_open(self.rate_url, data=dict(data, csrf_token=csrf))

    def _rating(self):
        self.env.invalidate_all()
        return (
            self.env["rating.rating"]
            .sudo()
            .search(
                [
                    ("res_model", "=", self.item._name),
                    ("res_id", "=", self.item.id),
                    ("partner_id", "=", self.author_user.partner_id.id),
                ]
            )
        )

    def test_held_comment_shown_to_author_only(self):
        self.authenticate("wlc_fm_author", "wlc_fm_author")
        response = self._rate(rating="1", feedback="What a SWINDLE this is")
        self.assertEqual(response.status_code, 200)
        rating = self._rating()
        self.assertEqual(rating.feedback_moderation_status, "pending")
        # The author lands on the rating card with the neutral notice and
        # still sees the own text in the reviews list. (Assertions use CSS
        # hooks, not copy: the page renders in the website's language.)
        html = self._page()
        self.assertEqual(html.count("wlc-feedback-notice"), 2)  # card + list
        self.assertIn("wlc-review-held", html)
        self.assertIn("What a SWINDLE this is", html)
        # The matched word is never named outside the author's own text.
        self.assertNotIn("swindle", html.lower().replace("what a swindle this is", ""))
        self.assertEqual(self.item.rating_count, 1)
        # Another user: the review card (stars) is there, no text, no notice.
        self.authenticate("wlc_fm_other", "wlc_fm_other")
        html = self._page()
        self.assertNotIn("What a SWINDLE this is", html)
        self.assertNotIn("wlc-feedback-notice", html)
        self.assertNotIn("wlc-review-held", html)
        self.assertIn("wlc-review-card", html)
        # Anonymous: same.
        self.authenticate(None, None)
        html = self._page()
        self.assertNotIn("What a SWINDLE this is", html)
        self.assertNotIn("wlc-feedback-notice", html)
        self.assertIn("wlc-review-card", html)

    def test_approved_comment_is_public_and_rejected_is_hidden(self):
        self.authenticate("wlc_fm_author", "wlc_fm_author")
        self._rate(rating="4", feedback="Lovely quiet place")
        rating = self._rating()
        self.assertEqual(rating.feedback_moderation_status, "approved")
        self.authenticate(None, None)
        self.assertIn("Lovely quiet place", self._page())

        rating.action_reject_feedback()
        html = self._page()
        self.assertNotIn("Lovely quiet place", html)
        self.assertIn("wlc-review-card", html)
        self.authenticate("wlc_fm_author", "wlc_fm_author")
        html = self._page()
        # Hidden from the author too (only the edit box still carries it).
        self.assertNotIn("Lovely quiet place", html.split("wlc-rate-form")[0])
        self.assertIn("wlc-feedback-notice", html)

    def test_delete_held_rating(self):
        manager = new_test_user(
            self.env,
            login="wlc_fm_web_manager",
            groups="base.group_user,website_local_content.group_local_content_manager",
        )
        self.authenticate("wlc_fm_author", "wlc_fm_author")
        self._rate(rating="2", feedback="a swindle")
        rating = self._rating()
        self.assertEqual(rating.feedback_moderation_status, "pending")
        activities = (
            self.env["mail.activity"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "res.partner"),
                    ("res_id", "=", self.author_user.partner_id.id),
                    ("user_id", "=", manager.id),
                ]
            )
        )
        self.assertEqual(len(activities), 1)
        self.env.invalidate_all()
        self.assertEqual(self.item.rating_count, 1)

        csrf = CSRF_PATTERN.search(self._page()).group(1)
        response = self.url_open(f"{self.rate_url}/delete", data={"csrf_token": csrf})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(self._rating())
        self.env.invalidate_all()
        self.assertEqual(self.item.rating_count, 0)
        self.assertAlmostEqual(self.item.rating_avg, 0.0, places=2)
        self.assertFalse(activities.exists(), "the moderation to-do is closed")
        self.assertNotIn("wlc-feedback-notice", self._page())

    def test_clean_comment_after_approval_needs_no_review(self):
        self.authenticate("wlc_fm_author", "wlc_fm_author")
        self._rate(rating="2", feedback="swindle")
        self._rating().action_approve_feedback()
        # Re-posting the same text with other stars keeps the approval.
        self._rate(rating="5", feedback="swindle")
        self.assertEqual(self._rating().feedback_moderation_status, "approved")
        self.assertNotIn("wlc-feedback-notice", self._page())
