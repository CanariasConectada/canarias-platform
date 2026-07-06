# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import werkzeug.exceptions
import werkzeug.utils

from odoo import http
from odoo.http import request
from odoo.tools import str2bool

from odoo.addons.portal.controllers.portal import pager as portal_pager

REVIEWS_PER_PAGE = 10


class PartnerReviewsController(http.Controller):
    """Public reviews page of a merchant website (``/resenas``).

    The merchant is resolved from the requested website itself (one company
    per website in this platform), never from user input. All writes go
    through ``sudo()`` with explicit ownership checks, mirroring how portal
    controllers deal with the restrictive core ACLs of ``rating.rating``.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_current_merchant(self):
        """Company owning the current website, if it accepts reviews."""
        website = request.website
        company = website and website.sudo().company_id
        if company and company.enable_reviews:
            return company
        return None

    def _get_user_review(self, company):
        """Existing review of the logged-in user for this merchant."""
        if request.env.user._is_public():
            return request.env["rating.rating"].sudo()
        return (
            request.env["rating.rating"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "res.company"),
                    ("res_id", "=", company.id),
                    ("partner_id", "=", request.env.user.partner_id.id),
                    ("consumed", "=", True),
                ],
                limit=1,
            )
        )

    def _get_status_message(self, status):
        """Feedback message after a redirect, keyed by a safe identifier so
        no free text ever travels in the query string."""
        _ = request.env._
        return {
            "saved": _("Thank you! Your review has been published."),
            "updated": _("Your review has been updated."),
            "pending": _(
                "Your review is awaiting moderation and will be published "
                "after a manual check."
            ),
            "deleted": _("Your review has been deleted."),
            "invalid_rating": _("Please select a rating between 1 and 5 stars."),
        }.get(status)

    def _comments_allowed(self):
        param = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param("partner_reviews.allow_comments", "True")
        )
        return str2bool(param, default=True)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @http.route("/resenas", auth="public", website=True)
    def reviews_page(self, page=1, status=None, **kwargs):
        company = self._get_current_merchant()
        if not company:
            raise werkzeug.exceptions.NotFound()

        Rating = request.env["rating.rating"].sudo()
        domain = company._get_review_domain()
        total = Rating.search_count(domain)
        pager = portal_pager(
            url="/resenas",
            total=total,
            page=int(page),
            step=REVIEWS_PER_PAGE,
        )
        reviews = Rating.search(
            domain,
            order="create_date desc",
            offset=pager["offset"],
            limit=REVIEWS_PER_PAGE,
        )
        return request.render(
            "partner_reviews.reviews_page",
            {
                "company": company,
                "reviews": reviews,
                "pager": pager,
                "total_reviews": total,
                "distribution": company._get_review_distribution(),
                "user_review": self._get_user_review(company),
                "comments_allowed": self._comments_allowed(),
                "status_message": self._get_status_message(status),
                "status_is_error": status == "invalid_rating",
            },
        )

    @http.route(
        "/resenas/enviar",
        auth="user",
        website=True,
        type="http",
        methods=["POST"],
    )
    def submit_review(self, rating=None, feedback=None, **kwargs):
        company = self._get_current_merchant()
        if not company:
            raise werkzeug.exceptions.NotFound()
        try:
            rating_value = int(rating)
        except (TypeError, ValueError):
            rating_value = 0
        if not 1 <= rating_value <= 5:
            return self._redirect_with_status("invalid_rating")

        feedback = (feedback or "").strip()
        if not self._comments_allowed():
            feedback = ""
        review = self._get_user_review(company)
        if review:
            review.write({"rating": rating_value, "feedback": feedback})
            status = "pending" if review.moderation_status == "pending" else "updated"
        else:
            review = (
                request.env["rating.rating"]
                .sudo()
                .create(
                    {
                        "res_model_id": request.env["ir.model"]._get_id("res.company"),
                        "res_id": company.id,
                        "partner_id": request.env.user.partner_id.id,
                        "rating": rating_value,
                        "feedback": feedback,
                        "consumed": True,
                    }
                )
            )
            status = "pending" if review.moderation_status == "pending" else "saved"
        return self._redirect_with_status(status)

    @http.route(
        "/resenas/eliminar",
        auth="user",
        website=True,
        type="http",
        methods=["POST"],
    )
    def delete_review(self, **kwargs):
        company = self._get_current_merchant()
        if not company:
            raise werkzeug.exceptions.NotFound()
        review = self._get_user_review(company)
        if review:
            review.unlink()
        return self._redirect_with_status("deleted")

    def _redirect_with_status(self, status):
        return werkzeug.utils.redirect(f"/resenas?status={status}")
