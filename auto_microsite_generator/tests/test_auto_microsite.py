# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestAutoMicrosite(TransactionCase):
    def _homepage_page(self, website):
        return self.env["website.page"].search(
            [("website_id", "=", website.id), ("url", "=", "/")], limit=1
        )

    # ------------------------------------------------------------------
    # Happy path
    # ------------------------------------------------------------------
    def test_create_company_generates_microsite(self):
        company = self.env["res.company"].create({"name": "Fresh Shop"})
        website = company.website_id
        self.assertTrue(website, "A website must be provisioned for the company.")

        page = self._homepage_page(website)
        self.assertTrue(page, "A homepage at '/' must exist.")
        self.assertEqual(
            page.view_id.key,
            f"auto_microsite_generator.homepage_{company.id}",
        )
        self.assertTrue(page.is_published)

        directory = self.env["website.menu"].search(
            [("website_id", "=", website.id), ("url", "=", "/comercio")]
        )
        self.assertTrue(directory, "The Directory menu entry must be created.")

    def test_homepage_renders_company_name(self):
        company = self.env["res.company"].create({"name": "Rendered Shop"})
        html = str(
            self.env["ir.qweb"]._render(
                "auto_microsite_generator.default_homepage_content",
                {"website": company.website_id},
            )
        )
        self.assertIn("Rendered Shop", html)

    def test_menu_creation_is_idempotent(self):
        company = self.env["res.company"].create({"name": "Idempotent Shop"})
        website = company.website_id
        Menu = self.env["website.menu"]
        before = Menu.search_count(
            [("website_id", "=", website.id), ("url", "=", "/comercio")]
        )
        company._auto_generate_microsite()
        after = Menu.search_count(
            [("website_id", "=", website.id), ("url", "=", "/comercio")]
        )
        self.assertEqual(before, 1)
        self.assertEqual(after, 1, "Re-running must not duplicate menu entries.")

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    def test_protected_company_skipped(self):
        company = self.env["res.company"].create({"name": "Zona Comercial Centro"})
        self.assertFalse(company.website_id)

    def test_no_microsite_auto_context(self):
        company = (
            self.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "Silent Shop"})
        )
        self.assertFalse(company.website_id)

    def test_disabled_by_system_parameter(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.enabled", "False"
        )
        company = self.env["res.company"].create({"name": "Disabled Shop"})
        self.assertFalse(company.website_id)

    # ------------------------------------------------------------------
    # Migration guard (plan-maestro section 2.4): never overwrite COW pages
    # ------------------------------------------------------------------
    def test_does_not_overwrite_migrated_homepage(self):
        # A company whose website + "/" page were brought by the migration.
        company = (
            self.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "Migrated Shop"})
        )
        website = self.env["website"].create(
            {"name": "Migrated Shop WS", "company_id": company.id}
        )
        company.invalidate_recordset(["website_id"])

        page = self._homepage_page(website)
        sentinel = (
            '<t t-name="auto_microsite_generator.homepage_migrated">'
            "<div>MIGRATED COW CONTENT</div></t>"
        )
        page.view_id.write({"arch_db": sentinel})
        # Anchor the page to the migration module, exactly like the data
        # migration does (external id canarias_mig.*).
        self.env["ir.model.data"].create(
            {
                "module": "canarias_mig",
                "name": f"website_page_{page.id}",
                "model": "website.page",
                "res_id": page.id,
            }
        )

        # Re-run generation: it must leave the migrated homepage untouched.
        company._auto_generate_microsite()

        page = self._homepage_page(website)
        self.assertIn("MIGRATED COW CONTENT", page.view_id.arch_db)
        self.assertEqual(
            self.env["website.page"].search_count(
                [("website_id", "=", website.id), ("url", "=", "/")]
            ),
            1,
            "The migrated homepage must not be duplicated.",
        )

    def test_migrated_menu_left_untouched(self):
        company = (
            self.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "Migrated Menu Shop"})
        )
        website = self.env["website"].create(
            {"name": "Migrated Menu WS", "company_id": company.id}
        )
        company.invalidate_recordset(["website_id"])

        root = self.env["website.menu"].search(
            [("website_id", "=", website.id), ("parent_id", "=", False)],
            limit=1,
        )
        migrated_menu = self.env["website.menu"].create(
            {
                "name": "Migrated Section",
                "url": "/migrated",
                "parent_id": root.id,
                "website_id": website.id,
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "canarias_mig",
                "name": f"website_menu_{migrated_menu.id}",
                "model": "website.menu",
                "res_id": migrated_menu.id,
            }
        )

        self.assertTrue(company._microsite_has_migrated_content(website))
        # Menu step is skipped, so no /comercio entry is injected.
        company._auto_generate_microsite()
        self.assertFalse(
            self.env["website.menu"].search_count(
                [("website_id", "=", website.id), ("url", "=", "/comercio")]
            )
        )
