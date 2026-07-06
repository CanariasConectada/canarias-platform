# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

REVIEWS_PAGE_URL = "/resenas"
REVIEWS_MENU_SEQUENCE = 50


class ResCompany(models.Model):
    """Each merchant is a company with its own website (one per company).

    Reviews are native ``rating.rating`` records pointing at the company
    (``res_model='res.company'``), so no ad-hoc review model is needed. The
    ``rating.mixin`` is deliberately NOT used here: it would inject the whole
    ``mail.thread`` machinery into ``res.company``; the two aggregates below
    are cheap to compute directly.
    """

    _inherit = "res.company"

    enable_reviews = fields.Boolean(
        string="Enable Reviews Page",
        default=False,
        help="Publish a reviews page on this company's website where "
        "customers can rate the business and leave comments.",
    )
    review_count = fields.Integer(compute="_compute_review_stats")
    review_avg = fields.Float(
        string="Average Rating",
        compute="_compute_review_stats",
        digits=(3, 1),
    )

    # ------------------------------------------------------------------
    # Review helpers
    # ------------------------------------------------------------------
    def _get_review_domain(self):
        """Public reviews of these companies (approved and filled in)."""
        return [
            ("res_model", "=", "res.company"),
            ("res_id", "in", self.ids),
            ("consumed", "=", True),
            ("moderation_status", "=", "approved"),
            ("rating", ">=", 1),
        ]

    def _compute_review_stats(self):
        grouped = (
            self.env["rating.rating"]
            .sudo()
            ._read_group(
                self._get_review_domain(),
                ["res_id"],
                ["__count", "rating:avg"],
            )
        )
        stats = {res_id: (count, avg) for res_id, count, avg in grouped}
        for company in self:
            count, avg = stats.get(company.id, (0, 0.0))
            company.review_count = count
            company.review_avg = avg or 0.0

    def _get_review_distribution(self):
        """Number of public reviews per star value: ``{1: n, ..., 5: n}``."""
        self.ensure_one()
        grouped = (
            self.env["rating.rating"]
            .sudo()
            ._read_group(self._get_review_domain(), ["rating"], ["__count"])
        )
        distribution = dict.fromkeys(range(1, 6), 0)
        for rating, count in grouped:
            star = min(5, max(1, int(round(rating))))
            distribution[star] += count
        return distribution

    def action_view_reviews(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "partner_reviews.action_partner_reviews"
        )
        action["domain"] = [
            ("res_model", "=", "res.company"),
            ("res_id", "=", self.id),
        ]
        return action

    # ------------------------------------------------------------------
    # Website menu synchronisation
    # ------------------------------------------------------------------
    def write(self, vals):
        result = super().write(vals)
        if "enable_reviews" in vals:
            self._sync_reviews_website_menu()
        return result

    def _sync_reviews_website_menu(self):
        """Add or remove the ``/resenas`` entry on the company website menu."""
        menu_model = self.env["website.menu"].sudo()
        for company in self:
            website = company.website_id
            if not website:
                continue
            menu = menu_model.search(
                [("website_id", "=", website.id), ("url", "=", REVIEWS_PAGE_URL)]
            )
            if company.enable_reviews and not menu:
                menu_model.create(
                    {
                        "name": self.env._("Reviews"),
                        "url": REVIEWS_PAGE_URL,
                        "website_id": website.id,
                        "parent_id": website.menu_id.id,
                        "sequence": REVIEWS_MENU_SEQUENCE,
                    }
                )
            elif not company.enable_reviews and menu:
                menu.unlink()

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        companies.filtered("enable_reviews")._sync_reviews_website_menu()
        return companies
