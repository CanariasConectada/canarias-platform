# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from .common import hero_h1_pattern, render_homepage_for


@tagged("post_install", "-at_install")
class TestMicrositeTitle(TransactionCase):
    """`microsite_title` is the one place that decides what the cover shows.

    This module knows two values only: the cover title the merchant typed
    and the legal name. The trade name joins the chain in the directory
    bridge, which has its own tests.
    """

    def _company(self, name, **extra):
        vals = {"name": name}
        vals.update(extra)
        return self.env["res.company"].create(vals)

    def test_the_cover_title_wins(self):
        company = self._company("Title Legal Test", microsite_name="La Tahona Test")
        self.assertEqual(company.microsite_title, "La Tahona Test")

    def test_an_empty_cover_title_falls_back_to_the_company_name(self):
        company = self._company("Title Legal Test")
        self.assertEqual(company.microsite_title, "Title Legal Test")

    def test_whitespace_counts_as_empty_and_the_title_is_stripped(self):
        company = self._company("Title Legal Test", microsite_name="   ")
        self.assertEqual(company.microsite_title, "Title Legal Test")
        company.microsite_name = "  La Tahona Test  "
        self.assertEqual(company.microsite_title, "La Tahona Test")

    def test_the_title_follows_the_company_name(self):
        company = self._company("Title Legal Test")
        company.name = "Title Renamed Test"
        self.assertEqual(company.microsite_title, "Title Renamed Test")

    def test_the_hero_and_the_lead_name_read_the_resolved_title(self):
        company = self._company("Title Legal Test", microsite_name="  La Tahona Test  ")
        html = render_homepage_for(self.env, company)
        self.assertRegex(html, hero_h1_pattern("La Tahona Test"))
        # The hidden lead name of the contact form reads the same field.
        self.assertIn('value="La Tahona Test"', html)
