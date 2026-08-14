# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged

from .common import PartnerReviewsCase


@tagged("post_install", "-at_install")
class TestReviewStats(PartnerReviewsCase):
    def test_stats_average_and_count(self):
        self._create_review(self.customer_1, 5)
        self._create_review(self.customer_2, 3)
        self.assertEqual(self.company.review_count, 2)
        self.assertAlmostEqual(self.company.review_avg, 4.0, places=1)

    def test_stats_ignore_pending_and_rejected(self):
        self._create_review(self.customer_1, 5)
        rejected = self._create_review(self.customer_2, 1)
        rejected.action_reject()
        self.company.invalidate_recordset(["review_count", "review_avg"])
        self.assertEqual(self.company.review_count, 1)
        self.assertAlmostEqual(self.company.review_avg, 5.0, places=1)

    def test_distribution(self):
        self._create_review(self.customer_1, 5)
        self._create_review(self.customer_2, 2)
        distribution = self.company._get_review_distribution()
        self.assertEqual(distribution[5], 1)
        self.assertEqual(distribution[2], 1)
        self.assertEqual(distribution[1], 0)

    def test_website_menu_sync(self):
        """Toggling the flag adds/removes the /resenas menu on the company
        website, when the company has one."""
        website = self.env["website"].create(
            {"name": "PR Test Website", "company_id": self.company.id}
        )
        # website_id on res.company is a stored compute without depends:
        # recompute it explicitly after creating the website.
        self.company._compute_website_id()
        self.assertEqual(self.company.website_id, website)
        Menu = self.env["website.menu"]
        self.company.enable_reviews = False
        self.assertFalse(
            Menu.search([("website_id", "=", website.id), ("url", "=", "/resenas")])
        )
        self.company.enable_reviews = True
        self.assertTrue(
            Menu.search([("website_id", "=", website.id), ("url", "=", "/resenas")])
        )
        self.company.enable_reviews = False
        self.assertFalse(
            Menu.search([("website_id", "=", website.id), ("url", "=", "/resenas")])
        )
