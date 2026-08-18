# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import HttpCase, tagged
from odoo.tests.common import TransactionCase

from odoo.addons.website_directory_company_certification.controllers.main import (
    WebsiteDirectoryCertification,
)


@tagged("post_install", "-at_install")
class TestDirectoryCertificationFilter(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.cert_type = cls.env.ref("company_certification.certification_type_silver")
        cls.certified_company = cls.env["res.company"].create(
            {"name": "Certified Dir Shop", "show_in_directory": True}
        )
        cls.plain_company = cls.env["res.company"].create(
            {"name": "Plain Dir Shop", "show_in_directory": True}
        )
        # Entries are normally synced by cron; force it for the test.
        (cls.certified_company + cls.plain_company)._sync_to_directory_entry()
        today = fields.Date.today()
        cls.env["res.company.certification"].create(
            {
                "company_id": cls.certified_company.id,
                "type_id": cls.cert_type.id,
                "level": "gold",
                "certification_date": today,
                "expiry_date": today + relativedelta(years=1),
                "score": 95.0,
            }
        )

    def _entries_matching(self, code):
        controller = WebsiteDirectoryCertification()
        domain = controller._get_certification_filter_domain(code)
        return self.env["website.directory.entry"].sudo().search(domain)

    def test_filter_domain_matches_only_certified(self):
        entries = self._entries_matching("silver")
        self.assertIn(
            self.certified_company,
            entries.mapped("company_id"),
        )
        self.assertNotIn(
            self.plain_company,
            entries.mapped("company_id"),
        )

    def test_expired_seal_filtered_out(self):
        status = self.certified_company.certification_ids
        status.expiry_date = fields.Date.today() - relativedelta(days=1)
        entries = self._entries_matching("silver")
        self.assertNotIn(self.certified_company, entries.mapped("company_id"))

    def test_valid_certifications_helper(self):
        self.assertEqual(
            self.certified_company._get_valid_certifications().type_id,
            self.cert_type,
        )
        self.assertFalse(self.plain_company._get_valid_certifications())


@tagged("post_install", "-at_install")
class TestDirectoryCertificationRendering(HttpCase):
    """The sidebar card as the visitor meets it."""

    def test_filter_card_carries_the_chip_styling_hook(self):
        """The card class is what the stylesheet hangs the legible chip
        treatment on; without it the chips fall back to the theme's amber
        outline with near-white text."""
        response = self.url_open("/comercio")
        self.assertEqual(response.status_code, 200)
        # The seed certification types ship with company_certification, so
        # the card renders on a bare database.
        self.assertIn("o_wdcc_filter", response.text)
