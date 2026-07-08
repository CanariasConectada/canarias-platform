# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from markupsafe import Markup

from odoo import _, api, fields, models

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
        result = super().write(vals)
        if "feedback" in vals:
            reviews = self.filtered(lambda r: r._is_merchant_review())
            reviews._apply_moderation()
            for review in reviews.filtered(lambda r: r.moderation_status == "pending"):
                review._notify_moderators()
        return result

    # ------------------------------------------------------------------
    # Moderation
    # ------------------------------------------------------------------
    def _apply_moderation(self):
        """Approve clean reviews, hold the ones with forbidden words."""
        if not self:
            return
        words = self.env["review.forbidden.word"].sudo().search([])
        for review in self:
            flagged = bool(words._match(review.feedback))
            review.write(
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
        group = self.env.ref(
            "partner_reviews.group_partner_reviews_moderator",
            raise_if_not_found=False,
        )
        if not group:
            return self.env["res.users"]
        return group.user_ids.filtered(lambda user: user.active)

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
            if activity_type_id and merchant_partner:
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
