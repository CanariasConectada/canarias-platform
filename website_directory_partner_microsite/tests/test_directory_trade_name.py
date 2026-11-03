# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDirectoryTradeName(TransactionCase):
    """The directory card shows the merchant's trade name, not the legal one.

    Measured 2026-09-02: 75 of 205 cards carried the legal name while the
    trade name sat on microsite_name, and every sync pass rewrote hand
    fixes back.
    """

    def _company(self, name, **extra):
        vals = {"name": name, "show_in_directory": True}
        vals.update(extra)
        return self.env["res.company"].create(vals)

    def test_the_trade_name_wins_on_the_card(self):
        company = self._company(
            "Dayra Test Legal SL", microsite_name="LA BELLE TEST"
        )
        self.assertEqual(
            company._prepare_directory_entry_values()["name"], "LA BELLE TEST"
        )

    def test_without_a_trade_name_the_legal_name_stays(self):
        company = self._company("Solo Legal Test SL")
        self.assertEqual(
            company._prepare_directory_entry_values()["name"], "Solo Legal Test SL"
        )

    def test_branches_sharing_a_trade_name_keep_their_legal_names(self):
        """Three identical cards would be worse than three formal ones."""
        first = self._company(
            "Academy Test Guanarteme", microsite_name="Academy Test"
        )
        second = self._company(
            "Academy Test San Jose", microsite_name="academy test "
        )
        self.assertEqual(
            first._prepare_directory_entry_values()["name"],
            "Academy Test Guanarteme",
        )
        self.assertEqual(
            second._prepare_directory_entry_values()["name"],
            "Academy Test San Jose",
        )

    def test_a_wildcard_in_the_trade_name_stays_a_letter(self):
        company = self._company("Percent Test SL", microsite_name="100% Canario Test")
        decoy = self._company("Decoy Test SL", microsite_name="100x Canario Test")
        self.assertEqual(
            company._prepare_directory_entry_values()["name"], "100% Canario Test"
        )
        self.assertEqual(
            decoy._prepare_directory_entry_values()["name"], "100x Canario Test"
        )
