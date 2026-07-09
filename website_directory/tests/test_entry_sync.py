# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import psycopg2.errors

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

# 1x1 red pixel, valid PNG.
PNG_PIXEL = (
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
    b"nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


@tagged("post_install", "-at_install")
class TestDirectoryEntrySync(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Entry = cls.env["website.directory.entry"]
        cls.Company = cls.env["res.company"]
        cls.root_category = cls.env["res.company.category"].create(
            {"name": "WD Test Root", "type": "view"}
        )
        cls.leaf_category = cls.env["res.company.category"].create(
            {
                "name": "WD Test Leaf",
                "type": "normal",
                "parent_id": cls.root_category.id,
            }
        )
        cls.company = cls.Company.create(
            {"name": "WD Test Company", "category_id": cls.leaf_category.id}
        )
        # Sync is asynchronous now (flagged on create/write, drained by cron):
        # flush the test company so entry-reading tests see the steady state.
        cls._flush(cls.company)

    @classmethod
    def _flush(cls, companies):
        """Run the async sync for the given companies, as the cron would."""
        companies._sync_to_directory_entry()
        companies.directory_sync_pending = False

    def _get_entry(self, company):
        return (
            self.Entry.sudo()
            .with_context(active_test=False)
            .search([("company_id", "=", company.id)])
        )

    def test_create_company_creates_entry(self):
        entry = self._get_entry(self.company)
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry.name, "WD Test Company")
        self.assertEqual(entry.zone, "canarias")
        self.assertTrue(entry.active)
        self.assertTrue(entry.is_published)

    def test_write_company_syncs_entry(self):
        self.company.write({"name": "WD Renamed Company"})
        self._flush(self.company)
        entry = self._get_entry(self.company)
        self.assertEqual(entry.name, "WD Renamed Company")

    def test_partner_contact_fields_sync(self):
        self.company.write({"phone": "+34 928 000 000", "city": "Las Palmas"})
        self._flush(self.company)
        entry = self._get_entry(self.company)
        self.assertEqual(entry.phone, "+34 928 000 000")
        self.assertEqual(entry.city, "Las Palmas")

    def test_category_related_from_company(self):
        entry = self._get_entry(self.company)
        self.assertEqual(entry.category_id, self.leaf_category)
        other_leaf = self.env["res.company.category"].create(
            {
                "name": "WD Other Leaf",
                "type": "normal",
                "parent_id": self.root_category.id,
            }
        )
        self.company.category_id = other_leaf
        self.assertEqual(entry.category_id, other_leaf)

    def test_show_in_directory_toggle(self):
        entry = self._get_entry(self.company)
        self.company.show_in_directory = False
        self._flush(self.company)
        self.assertFalse(entry.active)
        self.company.show_in_directory = True
        self._flush(self.company)
        self.assertTrue(entry.active)

    def test_archive_company_hides_entry(self):
        self.company.write({"active": False})
        self.assertFalse(self.company.show_in_directory)
        self._flush(self.company)
        entry = self._get_entry(self.company)
        self.assertFalse(entry.active)

    def test_logo_syncs_to_image(self):
        self.company.write({"logo": PNG_PIXEL})
        self._flush(self.company)
        entry = self._get_entry(self.company)
        self.assertTrue(entry.image_1920)
        self.assertTrue(entry.image_128)

    def test_sync_preserves_manual_fields(self):
        entry = self._get_entry(self.company)
        entry.write({"short_description": "Handmade bread", "is_published": False})
        self.company.write({"name": "WD Curated Company"})
        self._flush(self.company)
        self.assertEqual(entry.short_description, "Handmade bread")
        self.assertFalse(entry.is_published)

    @mute_logger("odoo.sql_db")
    def test_duplicate_active_entry_forbidden(self):
        # The partial unique index rejects the row at INSERT time.
        with self.assertRaises(
            psycopg2.errors.UniqueViolation
        ), self.env.cr.savepoint():
            self.Entry.create({"name": "Duplicate", "company_id": self.company.id})

    def test_archived_duplicate_allowed(self):
        entry = self.Entry.create(
            {
                "name": "Archived twin",
                "company_id": self.company.id,
                "active": False,
            }
        )
        self.assertFalse(entry.active)

    def test_get_display_name_fallbacks(self):
        entry = self._get_entry(self.company)
        partner = self.company.partner_id
        if "comercial" in partner._fields:
            partner.comercial = "WD Trade Name"
            self.assertEqual(entry.get_display_name(), "WD Trade Name")
            partner.comercial = False
        self.assertEqual(entry.get_display_name(), partner.name)

    def test_get_website_url_scheme(self):
        entry = self._get_entry(self.company)
        # No website anywhere on the company: placeholder, button hidden.
        self.assertEqual(entry.website_url, "#")
        self.assertEqual(entry.get_website_url(), "#")
        self.assertFalse(entry.has_external_website())
        self.company.partner_id.website = "http://wd-scheme.example.com"
        self.assertEqual(entry.get_website_url(), "http://wd-scheme.example.com")
        self.assertTrue(entry.has_external_website())

    def test_website_url_from_partner(self):
        # res.partner sanitizes bare domains by prefixing http://.
        self.company.write({"website": "https://wd-partner.example.com"})
        entry = self._get_entry(self.company)
        # No sync/flush needed: website_url is computed live from the
        # company, so the card URL can never go stale.
        self.assertEqual(entry.website_url, "https://wd-partner.example.com")

    def test_website_url_scheme_added(self):
        # A bare domain coming from the website record gets https:// added.
        website = self.env["website"].create(
            {"name": "WD Site", "domain": "wd-site.example.com"}
        )
        self.company.website_id = website
        entry = self._get_entry(self.company)
        self.assertEqual(entry.website_url, "https://wd-site.example.com")

    # ------------------------------------------------------------------
    # Async behaviour: create/write flag pending, the cron drains it
    # ------------------------------------------------------------------
    def test_create_flags_pending(self):
        company = self.Company.create({"name": "WD Pending Co"})
        self.assertTrue(company.directory_sync_pending)

    def test_write_trigger_flags_pending(self):
        self._flush(self.company)
        self.assertFalse(self.company.directory_sync_pending)
        self.company.write({"name": "WD Touched Co"})
        self.assertTrue(self.company.directory_sync_pending)

    def test_write_non_trigger_does_not_flag(self):
        self._flush(self.company)
        # ``email`` is a partner trigger field; a truly inert write must not
        # re-flag. Use a field outside the trigger set.
        self.company.write({"currency_id": self.company.currency_id.id})
        self.assertFalse(self.company.directory_sync_pending)

    def test_cron_syncs_and_clears_pending(self):
        company = self.Company.create({"name": "WD Cron Co"})
        self.assertTrue(company.directory_sync_pending)
        self.env["res.company"]._cron_sync_directory_entries()
        self.assertFalse(company.directory_sync_pending)
        entry = self._get_entry(company)
        self.assertEqual(entry.name, "WD Cron Co")

    def test_zone_hook_default(self):
        self.assertEqual(self.company._get_directory_zone(), "canarias")

    def test_category_badges_chain(self):
        entry = self._get_entry(self.company)
        badges = entry.get_category_badges()
        self.assertEqual(
            [badge["name"] for badge in badges], ["WD Test Root", "WD Test Leaf"]
        )
        self.assertEqual([badge["level"] for badge in badges], [1, 2])

    def test_zone_label_legacy_alias(self):
        entry = self._get_entry(self.company)
        self.assertEqual(entry.get_zone_label(), "Canarias Conectada")
        # Legacy rows may carry alternative spellings written before 5.0.
        self.env.cr.execute(
            "UPDATE website_directory_entry SET zone = %s WHERE id = %s",
            ("lomo_los_frailes", entry.id),
        )
        entry.invalidate_recordset(["zone"])
        self.assertEqual(entry.get_zone_label(), "Lomo los Frailes")
