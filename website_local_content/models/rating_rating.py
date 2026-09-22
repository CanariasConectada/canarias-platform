# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

LOCAL_CONTENT_MODEL = "website.local.content.item"
MODERATOR_GROUP = "website_local_content.group_local_content_manager"
ADMIN_GROUP = "base.group_system"
STATUS_FIELD = "feedback_moderation_status"


class RatingRating(models.Model):
    """Comment moderation of the local content ratings.

    A rating of a local content item (place of interest, living memory...)
    is a plain ``rating.rating`` row: stars in ``rating``, optional comment
    in ``feedback``. When the comment hits the shared forbidden-word list
    (``website_moderation_forbidden_word``) the STARS are published at once
    (they keep counting in the item's average) and only the comment text
    waits for a local content manager. This is deliberately narrower than
    the merchant reviews moderation of ``partner_reviews``, which holds the
    whole review; the two live side by side on the same model, on disjoint
    ``res_model`` values, with their own fields and actions.
    """

    _inherit = "rating.rating"

    feedback_moderation_status = fields.Selection(
        selection=[
            ("approved", "Published"),
            ("pending", "Pending review"),
            ("rejected", "Rejected"),
        ],
        string="Comment Status",
        default="approved",
        required=True,
        index=True,
        help="Local content ratings only. The stars always count; the comment "
        "text is held for a manager when it contains a forbidden word.",
    )

    def _is_local_content_rating(self):
        self.ensure_one()
        return self.res_model == LOCAL_CONTENT_MODEL

    @api.model_create_multi
    def create(self, vals_list):
        ratings = super().create(vals_list)
        local_ratings = ratings.filtered(lambda r: r._is_local_content_rating())
        local_ratings._apply_feedback_moderation()
        for rating in local_ratings:
            if rating.feedback_moderation_status == "pending":
                rating._notify_local_content_moderators()
        return ratings

    def write(self, vals):
        if STATUS_FIELD in vals:
            self._check_feedback_moderation_write_access()
        local_ratings = self.browse()
        previous = {}
        if "feedback" in vals:
            local_ratings = self.filtered(lambda r: r._is_local_content_rating())
            previous = {
                rating.id: (rating.feedback or "", rating.feedback_moderation_status)
                for rating in local_ratings
            }
        result = super().write(vals)
        if local_ratings:
            # Only a CHANGED text is re-evaluated. The public form re-saves
            # stars and comment together, so keeping the same comment while
            # changing the stars must neither undo a manager's approval nor
            # spawn another notification (which an author could otherwise
            # trigger at will).
            changed = local_ratings.filtered(
                lambda r: (r.feedback or "") != previous[r.id][0]
            )
            changed._apply_feedback_moderation()
            for rating in changed:
                if (
                    rating.feedback_moderation_status == "pending"
                    and previous[rating.id][1] != "pending"
                ):
                    rating._notify_local_content_moderators()
        return result

    def _check_feedback_moderation_write_access(self):
        """Only local content managers (or administrators) may change the
        comment status by hand. The moderation engine writes through
        ``sudo`` and is always allowed."""
        if self.env.su:
            return
        user = self.env.user
        if user.has_group(MODERATOR_GROUP) or user.has_group(ADMIN_GROUP):
            return
        raise AccessError(
            _("Only local content managers can change the comment status.")
        )

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------
    def _apply_feedback_moderation(self):
        """Publish clean comments, hold the ones with forbidden words.

        A rejected comment is re-evaluated like any other when its text
        changes (the caller only passes changed texts): the new text is a
        new comment. Unlike merchant reviews, there is nothing else to bring
        back, the stars were never hidden.
        """
        if not self:
            return
        words = self.env["moderation.forbidden.word"].sudo()
        for rating in self:
            flagged = words._contains_forbidden(rating.feedback)
            rating.sudo().write({STATUS_FIELD: "pending" if flagged else "approved"})

    def action_approve_feedback(self):
        self.write({STATUS_FIELD: "approved"})

    def action_reject_feedback(self):
        """Hide the comment for good; the text is kept for the audit trail
        and the stars keep counting."""
        self.write({STATUS_FIELD: "rejected"})

    # ------------------------------------------------------------------
    # Notifications (same pattern as partner_reviews)
    # ------------------------------------------------------------------
    @api.model
    def _get_local_content_moderators(self):
        """Active local content managers, or the system administrators when
        nobody holds the manager group yet."""
        for xmlid in (MODERATOR_GROUP, ADMIN_GROUP):
            group = self.env.ref(xmlid, raise_if_not_found=False)
            if not group:
                continue
            # ``all_user_ids``: explicit members and users holding the group
            # through an implied one.
            users = group.all_user_ids.filtered(
                lambda user: user.active and not user.share
            )
            if users:
                return users
        return self.env["res.users"]

    def _notify_local_content_moderators(self):
        """Email + to-do activity for every local content moderator.

        Neither ``rating.rating`` nor the content item is a ``mail.thread``,
        so the to-do is scheduled on the comment author's partner record,
        one open activity per (moderator, author) at a time.

        ``skip_review_notifications`` in the context silences everything,
        the same key ``partner_reviews`` honours: bulk imports must never
        spam the moderators.
        """
        if self.env.context.get("skip_review_notifications"):
            return
        self.ensure_one()
        moderators = self._get_local_content_moderators()
        if not moderators:
            return
        template = self.env.ref(
            "website_local_content.mail_template_comment_moderation",
            raise_if_not_found=False,
        )
        activity_type_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        author = self.partner_id
        partner_model_id = self.env["ir.model"]._get_id("res.partner")
        for user in moderators:
            if (
                activity_type_id
                and author
                and not self._pending_comment_activity_exists(
                    activity_type_id, user, author
                )
            ):
                self.env["mail.activity"].sudo().create(
                    {
                        "activity_type_id": activity_type_id,
                        "summary": _("Local content comment pending review"),
                        "note": _(
                            "The comment of %(author)s on %(item)s contains "
                            "words that require a manual check.",
                            author=author.name,
                            item=self.res_name,
                        ),
                        "user_id": user.id,
                        "res_id": author.id,
                        "res_model_id": partner_model_id,
                    }
                )
            if template and user.email:
                template.sudo().send_mail(
                    self.id, email_values={"email_to": user.email}
                )

    def _pending_comment_activity_exists(self, activity_type_id, user, author):
        return bool(
            self.env["mail.activity"]
            .sudo()
            .search_count(
                [
                    ("activity_type_id", "=", activity_type_id),
                    ("user_id", "=", user.id),
                    ("res_model", "=", author._name),
                    ("res_id", "=", author.id),
                ],
                limit=1,
            )
        )
