# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCompanyZone(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Company = cls.env["res.company"]
        cls.Entry = cls.env["website.directory.entry"].sudo()

    def _entry_of(self, company):
        company._sync_to_directory_entry()
        company.directory_sync_pending = False
        return self.Entry.with_context(active_test=False).search(
            [("company_id", "=", company.id)], limit=1
        )

    def test_new_company_defaults_to_the_global_zone(self):
        company = self.Company.create({"name": "RCZ Sin Zona"})
        self.assertEqual(company.commercial_zone, "canarias")
        self.assertEqual(self._entry_of(company).zone, "canarias")

    def test_zone_reaches_the_directory_entry(self):
        """The point of the module: website_directory left
        ``_get_directory_zone`` returning the global zone for everyone, so the
        public zone filter matched nothing."""
        company = self.Company.create(
            {"name": "RCZ Guanarteme", "commercial_zone": "guanarteme"}
        )
        self.assertEqual(self._entry_of(company).zone, "guanarteme")

    def test_changing_the_zone_updates_an_existing_entry(self):
        """The base sync only sets the zone on creation. The company form is
        where the zone is meant to be edited, so a later change must win or
        the directory keeps filtering by a stale value."""
        company = self.Company.create({"name": "RCZ Mudanza"})
        entry = self._entry_of(company)
        self.assertEqual(entry.zone, "canarias")
        company.commercial_zone = "tamaraceite"
        entry.invalidate_recordset()
        self.assertEqual(entry.zone, "tamaraceite")

    def test_legacy_spellings_are_normalised(self):
        """The old database wrote the same zone three ways, which is why
        website_directory had to carry ZONE_ALIASES at all."""
        for raw in ("lomo_los_frailes", "Lomo Los Frailes", "lomolosfrailes"):
            with self.subTest(raw=raw):
                self.assertEqual(self.Company._normalise_zone(raw), "lomolosfrailes")

    def test_unknown_zone_falls_back_instead_of_raising(self):
        """A migration feeding an unmapped code must not abort the run: the
        business lands in the global zone and stays visible."""
        self.assertEqual(self.Company._normalise_zone("barrio_inventado"), "canarias")
        self.assertEqual(self.Company._normalise_zone(""), "canarias")
        self.assertEqual(self.Company._normalise_zone(None), "canarias")

    def test_zone_is_a_sync_trigger_field(self):
        self.assertIn("commercial_zone", self.Company._get_directory_sync_fields())
