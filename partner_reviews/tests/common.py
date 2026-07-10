# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase


class PartnerReviewsCase(TransactionCase):
    """Shared fixtures: one merchant company and two customer partners."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_reset_password=True))
        cls.company = cls.env["res.company"].create(
            {"name": "PR Test Bakery", "enable_reviews": True}
        )
        cls.customer_1 = cls.env["res.partner"].create(
            {"name": "PR Customer One", "email": "pr.customer1@example.com"}
        )
        cls.customer_2 = cls.env["res.partner"].create(
            {"name": "PR Customer Two", "email": "pr.customer2@example.com"}
        )
        cls.company_model_id = cls.env["ir.model"]._get_id("res.company")

    def _create_review(self, partner, rating, feedback="", company=None):
        return self.env["rating.rating"].create(
            {
                "res_model_id": self.company_model_id,
                "res_id": (company or self.company).id,
                "partner_id": partner.id,
                "rating": rating,
                "feedback": feedback,
                "consumed": True,
            }
        )

    def _create_moderator(self, login, company=None):
        """A review moderator scoped to ``company`` (defaults to the bakery)."""
        company = company or self.company
        return self.env["res.users"].create(
            {
                "name": "PR Moderator %s" % login,
                "login": login,
                "email": "%s@example.com" % login,
                "company_id": company.id,
                "company_ids": [(6, 0, [company.id])],
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
