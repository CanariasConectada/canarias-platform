# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

MODERATOR_GROUP = "partner_reviews.group_partner_reviews_moderator"

# Merchant reviews are native rating.rating records attached to res.company.
MERCHANT_REVIEW_MODEL = "res.company"


class RatingRating(models.Model):
    """Moderation layer on top of the native rating model.

    A *merchant review* is a plain ``rating.rating`` record whose
    ``res_model`` is ``res.company``: stars in ``rating``, customer comment
    in ``feedback``, merchant answer in the native ``publisher_comment``
    (from ``portal_rating``). This module only adds the moderation state
    machine and the notifications; everything else is core.
    """

    _inherit = "rating.rating"

    moderation_status = fields.Selection(
        selection=[
            ("pending", "Pending moderation"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="approved",
        required=True,
        index=True,
        help="Only approved reviews are shown on the public website.",
    )
    requires_moderation = fields.Boolean(
        string="Contains Forbidden Words",
        readonly=True,
        help="Set automatically when the customer comment matches an entry "
        "of the forbidden words list.",
    )

    # One consumed review per customer and merchant. Partial index so the
    # rule only applies to merchant reviews, never to ratings created by
    # other apps (helpdesk, projects...) on their own models.
    _merchant_review_uniq = models.UniqueIndex(
        "(res_id, partner_id) WHERE res_model = 'res.company' AND consumed IS TRUE",
        "You have already reviewed this business. Edit your existing review instead.",
    )

    def _is_merchant_review(self):
        self.ensure_one()
        return self.res_model == MERCHANT_REVIEW_MODEL

    @api.model_create_multi
    def create(self, vals_list):
        ratings = super().create(vals_list)
        merchant_reviews = ratings.filtered(lambda r: r._is_merchant_review())
        merchant_reviews._apply_moderation()
        for review in merchant_reviews:
            if review.moderation_status == "pending":
                review._notify_moderators()
            else:
                review._notify_merchant()
        return ratings

    def write(self, vals):
        if "moderation_status" in vals:
            self._check_moderation_write_access()
        feedback_changed = "feedback" in vals
        if feedback_changed:
            merchant_reviews = self.filtered(lambda r: r._is_merchant_review())
            # Snapshot the status BEFORE re-moderation so we only notify on a
            # real transition into ``pending``. A review that was already
            # ``pending`` must not spawn a fresh email + activity on every
            # edit, otherwise an author could flood every moderator by
            # re-saving forbidden feedback N times (DoS).
            previous_status = {
                review.id: review.moderation_status for review in merchant_reviews
            }
        result = super().write(vals)
        if feedback_changed:
            merchant_reviews._apply_moderation()
            for review in merchant_reviews:
                if (
                    review.moderation_status == "pending"
                    and previous_status.get(review.id) != "pending"
                ):
                    review._notify_moderators()
        return result

    def _check_moderation_write_access(self):
        """Only review moderators may change ``moderation_status`` directly.

        The native ``rating.rating`` ACL grants write to every internal user
        (see ``security/partner_reviews_rules.xml``), so without this guard any
        employee could approve a held review over RPC and bypass moderation.
        The moderation engine itself (``_apply_moderation``) writes through
        ``sudo`` and is therefore always allowed, as is any superuser flow.
        """
        if self.env.su:
            return
        if self.env.user.has_group(MODERATOR_GROUP):
            return
        raise AccessError(
            _("Only review moderators can change the moderation status.")
        )

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------
    def _apply_moderation(self):
        """Approve clean reviews, hold the ones with forbidden words.

        ``rejected`` is a TERMINAL state: once a moderator has turned a
        review down, re-running moderation (typically after the customer
        edits the feedback) must never silently bring it back to
        ``approved``. Only an explicit moderator action (``action_approve``)
        can move a review out of ``rejected``.
        """
        if not self:
            return
        words = self.env["review.forbidden.word"].sudo().search([])
        for review in self:
            if review.moderation_status == "rejected":
                continue
            flagged = bool(words._match(review.feedback))
            # Written through ``sudo``: ``moderation_status`` is a system-managed
            # field (guarded by ``_check_moderation_write_access``); only the
            # moderation engine and explicit moderator actions may set it.
            review.sudo().write(
                {
                    "requires_moderation": flagged,
                    "moderation_status": "pending" if flagged else "approved",
                }
            )

    def action_approve(self):
        self.write({"moderation_status": "approved"})
        for review in self.filtered(lambda r: r._is_merchant_review()):
            review._notify_merchant()

    def action_reject(self):
        self.write({"moderation_status": "rejected"})

    # ------------------------------------------------------------------
    # Notifications
    # ------------------------------------------------------------------
    def _get_moderator_users(self):
        """Active moderators allowed on this review's merchant company.

        A merchant review stores the company id in ``res_id``; only moderators
        who have that company among their allowed ones (``company_ids``) are
        notified, so a review of company A never leaks to a moderator scoped to
        company B.
        """
        self.ensure_one()
        group = self.env.ref(MODERATOR_GROUP, raise_if_not_found=False)
        if not group:
            return self.env["res.users"]
        moderators = group.user_ids.filtered(lambda user: user.active)
        if self._is_merchant_review():
            company_id = self.res_id
            moderators = moderators.filtered(
                lambda user: company_id in user.company_ids.ids
            )
        return moderators

    def _notify_moderators(self):
        """Email + to-do activity for every review moderator.

        ``rating.rating`` is not a ``mail.thread``, so the to-do activity is
        scheduled on the merchant's partner record instead of on the review.
        """
        self.ensure_one()
        moderators = self._get_moderator_users()
        if not moderators:
            return
        template = self.env.ref(
            "partner_reviews.mail_template_review_moderation",
            raise_if_not_found=False,
        )
        activity_type_id = self.env["ir.model.data"]._xmlid_to_res_id(
            "mail.mail_activity_data_todo", raise_if_not_found=False
        )
        merchant_partner = (
            self.env[MERCHANT_REVIEW_MODEL].sudo().browse(self.res_id).partner_id
        )
        for user in moderators:
            if (
                activity_type_id
                and merchant_partner
                and not self._pending_activity_exists(
                    activity_type_id, user, merchant_partner
                )
            ):
                self.env["mail.activity"].sudo().create(
                    {
                        "activity_type_id": activity_type_id,
                        "summary": _("Review pending moderation"),
                        "note": _(
                            "The review of %(author)s on %(merchant)s contains "
                            "words that require a manual check.",
                            author=self.partner_id.name or _("a visitor"),
                            merchant=self.res_name,
                        ),
                        "user_id": user.id,
                        "res_id": merchant_partner.id,
                        "res_model_id": self.env["ir.model"]._get_id(
                            merchant_partner._name
                        ),
                    }
                )
            if template and user.email:
                template.sudo().send_mail(
                    self.id,
                    email_values={"email_to": user.email},
                )

    def _pending_activity_exists(self, activity_type_id, user, merchant_partner):
        """Whether a moderation to-do is already open for this moderator.

        Deduplicates the to-do per (moderator, merchant partner): a second
        notification while the previous one is still open must not pile up
        another activity on the moderator's dashboard.
        """
        return bool(
            self.env["mail.activity"].sudo().search_count(
                [
                    ("activity_type_id", "=", activity_type_id),
                    ("user_id", "=", user.id),
                    ("res_model", "=", merchant_partner._name),
                    ("res_id", "=", merchant_partner.id),
                ],
                limit=1,
            )
        )

    def _notify_merchant(self):
        """Plain email to the merchant when an approved review arrives."""
        self.ensure_one()
        company = self.env[MERCHANT_REVIEW_MODEL].sudo().browse(self.res_id)
        if not company.exists() or not company.email:
            return
        body = Markup(
            "<p>%(greeting)s</p><p>%(intro)s</p>"
            "<ul><li>%(author_label)s: %(author)s</li>"
            "<li>%(rating_label)s: %(rating)s/5</li>"
            "<li>%(comment_label)s: %(comment)s</li></ul>"
        ) % {
            # Markup's % operator escapes every plain string value below.
            "greeting": _("Hello %s,", company.name),
            "intro": _("You have received a new review on your website:"),
            "author_label": _("Author"),
            "author": self.partner_id.name or _("A visitor"),
            "rating_label": _("Rating"),
            "rating": int(self.rating),
            "comment_label": _("Comment"),
            "comment": self.feedback or _("(no comment)"),
        }
        self.env["mail.mail"].sudo().create(
            {
                "subject": _("New review on %s", company.name),
                "body_html": body,
                "email_to": company.email,
                "auto_delete": True,
            }
        ).send()
