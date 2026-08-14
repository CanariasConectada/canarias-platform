# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMicrositeCompany(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # auto_microsite_generator (co-installed in the full image) overrides
        # res.company.create() to auto-provision a website per company, which
        # perturbs the website ids/microsite state these tests assert on.
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.company = cls.env["res.company"].create(
            {
                "name": "Microsite Test Company",
                "street": "Calle Mayor 1",
                "city": "Las Palmas",
                "zip": "35001",
            }
        )
        cls.website = cls.env["website"].create(
            {
                "name": "Microsite Test Website",
                "company_id": cls.company.id,
            }
        )
        # website_id on res.company is a stored compute: refresh it.
        cls.company.invalidate_recordset(["website_id"])

    def test_has_microsite(self):
        self.assertTrue(self.company.has_microsite)
        lonely = self.env["res.company"].create({"name": "No Website Co"})
        self.assertFalse(lonely.has_microsite)

    def test_partner_bridge(self):
        partner = self.company.partner_id
        self.assertTrue(partner.has_microsite)
        self.assertEqual(partner.microsite_company_id, self.company)
        action = partner.action_open_microsite_company()
        self.assertEqual(action["res_model"], "res.company")
        self.assertEqual(action["res_id"], self.company.id)

    def test_opening_hours_constraint_accepts_valid(self):
        self.company.microsite_opening_hours = (
            "L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00"
        )
        lines = self.company._get_microsite_opening_hours_lines()
        self.assertEqual(lines[0], ("Monday", "10:00 - 13:30 / 16:30 - 20:00"))
        self.assertEqual(lines[-1], ("Saturday", "10:00 - 14:00"))

    def test_opening_hours_constraint_rejects_garbage(self):
        with self.assertRaises(ValidationError):
            self.company.microsite_opening_hours = "open when sunny"

    def test_opening_hours_constraint_rejects_three_ranges(self):
        with self.assertRaises(ValidationError):
            self.company.microsite_opening_hours = (
                "L 08:00-10:00 / L 11:00-13:00 / L 15:00-18:00"
            )

    def test_map_url_from_address(self):
        url = self.company._get_microsite_map_url()
        self.assertIn("maps.google.com", url)
        self.assertIn("Calle+Mayor+1", url)

    def test_map_url_custom_wins(self):
        self.company.microsite_map_url = "https://example.com/embed"
        self.assertEqual(
            self.company._get_microsite_map_url(), "https://example.com/embed"
        )

    def test_map_url_rejects_javascript_scheme(self):
        with self.assertRaises(ValidationError):
            self.company.microsite_map_url = "javascript:alert(1)"

    def test_map_url_rejects_data_scheme(self):
        with self.assertRaises(ValidationError):
            self.company.microsite_map_url = (
                "data:text/html,<script>alert(1)</script>"
            )

    def test_map_url_rejects_http_scheme(self):
        with self.assertRaises(ValidationError):
            self.company.microsite_map_url = "http://insecure.example.com/embed"

    def test_map_url_rejects_obfuscated_javascript_scheme(self):
        # urlsplit strips the tab, so 'java\tscript:' must still be caught.
        with self.assertRaises(ValidationError):
            self.company.microsite_map_url = "java\tscript:alert(1)"

    def test_map_url_normalizes_missing_scheme(self):
        self.company.microsite_map_url = "maps.example.com/embed?q=Telde"
        self.assertEqual(
            self.company._get_microsite_map_url(),
            "https://maps.example.com/embed?q=Telde",
        )

    def test_map_url_empty_without_address(self):
        company = self.env["res.company"].create({"name": "Nowhere Co"})
        self.assertEqual(company._get_microsite_map_url(), "")

    def test_publish_homepage_creates_page(self):
        self.company.action_publish_microsite_homepage()
        page = self.company.microsite_homepage_page_id
        self.assertTrue(page)
        self.assertEqual(page.url, "/")
        self.assertEqual(page.website_id, self.website)
        self.assertTrue(page.is_published)
        self.assertIn(
            "partner_microsite_manager.microsite_homepage_content",
            page.view_id.arch_db,
        )

    def test_publish_homepage_is_idempotent(self):
        self.company.action_publish_microsite_homepage()
        first_page = self.company.microsite_homepage_page_id
        self.company.action_publish_microsite_homepage()
        self.assertEqual(self.company.microsite_homepage_page_id, first_page)
        pages = self.env["website.page"].search(
            [("website_id", "=", self.website.id), ("url", "=", "/")]
        )
        self.assertEqual(len(pages), 1)

    def test_publish_homepage_requires_website(self):
        lonely = self.env["res.company"].create({"name": "No Website Co 2"})
        with self.assertRaises(UserError):
            lonely.action_publish_microsite_homepage()

    def test_publish_homepage_denied_for_plain_user(self):
        # A plain internal user (no website designer role) must not be able
        # to overwrite the public homepage through the sudo publish action.
        plain_user = self.env["res.users"].create(
            {
                "name": "Plain PMM User",
                "login": "plain_pmm_user",
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertFalse(
            plain_user.has_group("website.group_website_designer")
        )
        with self.assertRaises(AccessError):
            self.company.with_user(
                plain_user
            ).action_publish_microsite_homepage()
