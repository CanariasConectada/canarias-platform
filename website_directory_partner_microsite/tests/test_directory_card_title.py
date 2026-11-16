# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestDirectoryCardTitle(TransactionCase):
    """The directory card reads the resolved cover title (19.0.2.2.0): cover
    title, trade name, legal name -- and re-syncs when any of them moves."""

    def _company(self, name, **extra):
        vals = {"name": name, "show_in_directory": True}
        vals.update(extra)
        return self.env["res.company"].create(vals)

    def _card_name(self, company):
        return company._prepare_directory_entry_values()["name"]

    # -- what the card shows ---------------------------------------------

    def test_the_trade_name_fills_an_empty_cover_title(self):
        company = self._company("Dayra Legal Test", comercial="La Belle Dog Test")
        self.assertFalse(company.microsite_name)
        self.assertEqual(self._card_name(company), "La Belle Dog Test")

    def test_a_trade_name_equal_to_the_legal_name_is_the_legal_name(self):
        company = self._company("Same Name Test", comercial="Same Name Test")
        self.assertEqual(self._card_name(company), "Same Name Test")

    def test_branches_sharing_a_trade_name_keep_their_legal_names(self):
        first = self._company("Astrid Triana Test", comercial="Churreria Astrid Test")
        second = self._company("Astrid Vegueta Test", comercial="churreria astrid test")
        self.assertEqual(self._card_name(first), "Astrid Triana Test")
        self.assertEqual(self._card_name(second), "Astrid Vegueta Test")

    def test_a_cover_title_and_a_trade_name_resolving_alike_are_twins(self):
        typed = self._company("Typed Legal Test", microsite_name="Twin X Test")
        inherited = self._company("Inherited Legal Test", comercial="twin x test")
        self.assertEqual(self._card_name(typed), "Typed Legal Test")
        self.assertEqual(self._card_name(inherited), "Inherited Legal Test")

    def test_an_archived_twin_does_not_count(self):
        """The cron runs with active_test=False; an archived legacy company
        still flagged for the directory must not push a live shop back to
        its legal name."""
        live = self._company("Live Legal Test", comercial="Lonely Sign Test")
        archived = self._company("Archived Legal Test", comercial="Lonely Sign Test")
        archived.active = False
        archived.show_in_directory = True
        self.assertEqual(
            self._card_name(live.with_context(active_test=False)), "Lonely Sign Test"
        )

    # -- when the card is re-synced -----------------------------------------

    def _settle(self, company):
        company.directory_sync_pending = False
        self.assertFalse(company.directory_sync_pending)

    def test_a_new_cover_title_flags_the_card_for_a_resync(self):
        company = self._company("Resync Legal Test")
        self._settle(company)
        company.write({"microsite_name": "New Cover Test"})
        self.assertTrue(company.directory_sync_pending)

    def test_a_new_trade_name_on_the_partner_flags_the_card_for_a_resync(self):
        company = self._company("Resync Legal Test")
        self._settle(company)
        company.partner_id.write({"comercial": "New Sign Test"})
        self.assertTrue(company.directory_sync_pending)

    def test_a_new_trade_name_on_the_company_flags_the_card_for_a_resync(self):
        company = self._company("Resync Legal Test")
        self._settle(company)
        company.write({"comercial": "New Sign Test"})
        self.assertTrue(company.directory_sync_pending)
