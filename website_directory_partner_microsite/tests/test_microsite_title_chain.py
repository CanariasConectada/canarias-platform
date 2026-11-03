# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.partner_microsite_manager.tests.common import (
    hero_h1_pattern,
    render_homepage_for,
)


@tagged("post_install", "-at_install")
class TestMicrositeTitleChain(TransactionCase):
    """With both halves installed the cover title resolves cover title, then
    trade name (`comercial`), then legal name."""

    def _company(self, name, **extra):
        vals = {"name": name}
        vals.update(extra)
        return self.env["res.company"].create(vals)

    def test_the_trade_name_fills_an_empty_cover_title(self):
        company = self._company("Dayra Legal Test", comercial="La Belle Dog Test")
        self.assertEqual(company.microsite_title, "La Belle Dog Test")

    def test_whitespace_in_the_trade_name_counts_as_empty(self):
        company = self._company("Dayra Legal Test", comercial="   ")
        self.assertEqual(company.microsite_title, "Dayra Legal Test")

    def test_without_either_the_legal_name_stays(self):
        company = self._company("Solo Legal Test")
        self.assertEqual(company.microsite_title, "Solo Legal Test")

    def test_the_cover_title_still_wins_over_the_trade_name(self):
        company = self._company(
            "Dayra Legal Test",
            comercial="La Belle Dog Test",
            microsite_name="La Belle Dog Peluqueria Test",
        )
        self.assertEqual(company.microsite_title, "La Belle Dog Peluqueria Test")

    def test_the_title_follows_the_trade_name_written_on_the_company(self):
        company = self._company("Dayra Legal Test", comercial="La Belle Dog Test")
        company.comercial = "La Belle Cat Test"
        self.assertEqual(company.microsite_title, "La Belle Cat Test")

    def test_the_title_follows_the_trade_name_written_on_the_partner(self):
        """Contacts edits the partner, never the company."""
        company = self._company("Dayra Legal Test", comercial="La Belle Dog Test")
        company.partner_id.write({"comercial": "La Belle Cat Test"})
        self.assertEqual(company.microsite_title, "La Belle Cat Test")

    def test_the_hero_shows_the_trade_name_when_the_cover_title_is_empty(self):
        company = self._company("Dayra Legal Test", comercial="La Belle Dog Test")
        html = render_homepage_for(self.env, company)
        self.assertRegex(html, hero_h1_pattern("La Belle Dog Test"))
        self.assertIn('value="La Belle Dog Test"', html)
