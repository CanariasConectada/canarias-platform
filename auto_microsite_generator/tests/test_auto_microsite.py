# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
import re
from pathlib import Path
from unittest.mock import patch

from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..hooks import uninstall_hook
from ..models.res_company import (
    LOCAL_GUIDE_CHILDREN,
    LOCAL_GUIDE_URLS,
    MICROSITE_CONTENT_DEFAULTS,
    _normalize_subdomain,
)

MIGRATION_2_2_0 = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "19.0.2.2.0"
    / "post-migration.py"
)


@tagged("post_install", "-at_install")
class TestAutoMicrosite(TransactionCase):
    def setUp(self):
        super().setUp()
        # These cases are about what a microsite is born WITH, not about who
        # names its subdomain, so they run in "auto" mode -- the historical
        # behaviour. The "ask" default is exercised on its own below, in
        # TestMicrositeSubdomain.
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "auto"
        )

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
        if hasattr(company, "_publish_microsite_homepage"):
            # partner_microsite_manager installed: born with the rich
            # corporate homepage instead of the generic hero.
            expected_key = f"partner_microsite_manager.microsite_homepage_{company.id}"
        else:
            expected_key = f"auto_microsite_generator.homepage_{company.id}"
        self.assertEqual(page.view_id.key, expected_key)
        self.assertTrue(page.is_published)

        directory = self.env["website.menu"].search(
            [("website_id", "=", website.id), ("url", "=", "/comercio")]
        )
        self.assertTrue(directory, "The Directory menu entry must be created.")

    def test_new_website_is_born_with_the_corporate_look(self):
        company = self.env["res.company"].create({"name": "Themed Shop"})
        website = company.website_id
        if "is_microsite_themed" not in website._fields:
            self.skipTest("partner_microsite_manager is not installed")
        self.assertTrue(
            website.is_microsite_themed,
            "A new microsite must be born with the corporate look.",
        )

    def test_domain_is_built_from_the_suffix_parameter(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.domain_suffix", ".canariasconectada.es"
        )
        company = self.env["res.company"].create({"name": "Routed Shop"})
        self.assertEqual(
            company.website_id.domain,
            "https://routedshop.canariasconectada.es",
            "A new microsite must be born routable under the production "
            "domain convention.",
        )

    def test_empty_suffix_parameter_warns_about_unroutable_site(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.domain_suffix", ""
        )
        logger_name = "odoo.addons.auto_microsite_generator.models.res_company"
        with self.assertLogs(logger_name, level="WARNING") as capture:
            company = self.env["res.company"].create({"name": "Unroutable Shop"})
        self.assertFalse(company.website_id.domain)
        self.assertTrue(
            any("domain_suffix" in message for message in capture.output),
            "An empty suffix must be flagged loudly: the site is unroutable.",
        )

    def test_zone_dropdown_is_created(self):
        company = self.env["res.company"].create({"name": "Zoned Shop"})
        website = company.website_id
        parent = self.env["website.menu"].search(
            [("website_id", "=", website.id), ("name", "=", "Zonas Comerciales")]
        )
        self.assertEqual(len(parent), 1, "The zone dropdown must exist once.")
        self.assertEqual(parent.url, "#")
        self.assertEqual(parent.sequence, 40)
        children = parent.child_id.sorted(key=lambda m: m.sequence)
        self.assertEqual(
            [(menu.name, menu.url) for menu in children],
            [
                ("Todas", "https://canariasconectada.es"),
                ("Guanarteme", "https://guanarteme.canariasconectada.es"),
                ("Lomo Los Frailes", "https://lomolosfrailes.canariasconectada.es"),
                ("Tamaraceite", "https://tamaraceite.canariasconectada.es"),
            ],
        )

    def test_stock_event_and_course_menus_are_pruned(self):
        company = self.env["res.company"].create({"name": "Pruned Shop"})
        website = company.website_id
        self.assertFalse(
            self.env["website.menu"].search_count(
                [
                    ("website_id", "=", website.id),
                    ("url", "in", ["/event", "/slides"]),
                ]
            ),
            "The stock Events/Courses entries must not survive on a new " "microsite.",
        )

    def test_prune_never_touches_an_existing_website(self):
        company = (
            self.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "Curated Menu Shop"})
        )
        website = self.env["website"].create(
            {"name": "Curated Menu WS", "company_id": company.id}
        )
        # website_id is a stored compute WITHOUT depends: flag it for
        # recomputation so the generation pass sees the EXISTING website
        # (a bare invalidation would leave it stale at False).
        self.env.add_to_compute(company._fields["website_id"], company)
        self.assertEqual(company.website_id, website)
        root = self.env["website.menu"].search(
            [("website_id", "=", website.id), ("parent_id", "=", False)],
            limit=1,
        )
        eventos = self.env["website.menu"].create(
            {
                "name": "Eventos",
                "url": "/event",
                "parent_id": root.id,
                "website_id": website.id,
            }
        )
        # Re-running generation on an EXISTING website must stay create-only.
        company._auto_generate_microsite()
        self.assertTrue(
            eventos.exists(),
            "The prune pass must never run on an already existing website.",
        )

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
        zone_domain = [
            ("website_id", "=", website.id),
            ("name", "=", "Zonas Comerciales"),
        ]
        zone_before = Menu.search_count(zone_domain)
        company._auto_generate_microsite()
        after = Menu.search_count(
            [("website_id", "=", website.id), ("url", "=", "/comercio")]
        )
        self.assertEqual(before, 1)
        self.assertEqual(after, 1, "Re-running must not duplicate menu entries.")
        self.assertEqual(zone_before, 1)
        self.assertEqual(
            Menu.search_count(zone_domain),
            1,
            "Re-running must not duplicate the zone dropdown.",
        )

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

    # ------------------------------------------------------------------
    # Fix 1: website_id is a stored compute without @api.depends, so it must
    # be flagged for recomputation (not merely invalidated) after generation.
    # ------------------------------------------------------------------
    def test_website_id_persists_on_fresh_browse(self):
        company = self.env["res.company"].create({"name": "Persisted Shop"})
        website = company.website_id
        self.assertTrue(website, "website_id must be set right after create.")

        # Force a full DB round-trip: flush pending writes, drop every cache,
        # then browse the company from scratch. A stale (False) stored value
        # would surface here.
        self.env.flush_all()
        self.env.invalidate_all()
        fresh = self.env["res.company"].browse(company.id)
        self.assertTrue(
            fresh.website_id,
            "website_id must survive as a stored value on a fresh browse.",
        )
        self.assertEqual(fresh.website_id, website)

    # ------------------------------------------------------------------
    # Fix 2: re-running generation must not churn the homepage view.
    # ------------------------------------------------------------------
    def test_homepage_generation_is_idempotent(self):
        company = self.env["res.company"].create({"name": "Stable Shop"})
        view = self._homepage_page(company.website_id).view_id
        self.assertTrue(view, "A homepage view must exist after the first pass.")

        self.env.flush_all()
        view.invalidate_recordset()
        before_write_date = view.write_date
        before_arch = view.arch_db

        # Second full generation pass must be a no-op for the homepage view.
        company._auto_generate_microsite()
        self.env.flush_all()
        view.invalidate_recordset()

        self.assertEqual(
            view.write_date,
            before_write_date,
            "Re-running generation must not rewrite the homepage view.",
        )
        self.assertEqual(view.arch_db, before_arch)

    # ------------------------------------------------------------------
    # Fix 3: a microsite failure must not roll back the company creation.
    # ------------------------------------------------------------------
    def test_microsite_failure_does_not_abort_company_create(self):
        def boom(self):
            raise ValueError("microsite kaboom")

        res_company = type(self.env["res.company"])
        with patch.object(res_company, "_auto_generate_microsite", boom):
            company = self.env["res.company"].create({"name": "Resilient Shop"})

        self.assertTrue(
            company.exists(),
            "The company must be created even if the microsite blows up.",
        )
        self.assertFalse(
            company.website_id,
            "The failed microsite must not have provisioned a website.",
        )

    # ------------------------------------------------------------------
    # Fix 4: uninstall must drop the runtime-generated homepages.
    # ------------------------------------------------------------------
    def test_uninstall_hook_removes_generated_homepages(self):
        # The hook cleans the GENERIC homepages (module key prefix). With
        # partner_microsite_manager installed a new company is born with the
        # rich homepage instead, so suppress the upgrade step to exercise
        # the generic path the hook is responsible for.
        res_company = type(self.env["res.company"])
        if hasattr(res_company, "_publish_microsite_homepage"):
            patcher = patch.object(
                res_company,
                "_publish_microsite_homepage",
                lambda self, website: None,
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        company = self.env["res.company"].create({"name": "Uninstall Shop"})
        page = self._homepage_page(company.website_id)
        view = page.view_id
        self.assertTrue(
            view.key.startswith("auto_microsite_generator.homepage_"),
            "The generated homepage view must carry the module key prefix.",
        )

        uninstall_hook(self.env)

        self.assertFalse(view.exists(), "The generated homepage view must be removed.")
        self.assertFalse(page.exists(), "The generated homepage page must be removed.")

    # ------------------------------------------------------------------
    # Fix 5: accented company names produce ASCII subdomains.
    # ------------------------------------------------------------------
    def test_subdomain_transliterates_accents(self):
        self.assertEqual(_normalize_subdomain("Panadería Ñandú"), "panaderianandu")
        self.assertEqual(_normalize_subdomain("Über Grün"), "ubergrun")
        self.assertEqual(_normalize_subdomain("   "), "empresa")

    # ------------------------------------------------------------------
    # Content defaults: a new microsite must not be born as an empty shell.
    # ------------------------------------------------------------------
    def test_new_microsite_is_born_with_content_defaults(self):
        company = self.env["res.company"].create({"name": "Seeded Shop"})
        if "microsite_about_text" not in company._fields:
            self.skipTest("partner_microsite_manager is not installed.")
        for field, value in MICROSITE_CONTENT_DEFAULTS.items():
            self.assertEqual(
                company[field],
                value,
                f"{field} must be seeded so its homepage section renders.",
            )

    def test_content_defaults_never_overwrite_existing_copy(self):
        if "microsite_about_text" not in self.env["res.company"]._fields:
            self.skipTest("partner_microsite_manager is not installed.")
        company = self.env["res.company"].create(
            {
                "name": "Opinionated Shop",
                "microsite_about_text": "Our own words.",
                "microsite_button_text": "Catálogo",
            }
        )
        self.assertEqual(company.microsite_about_text, "Our own words.")
        self.assertEqual(company.microsite_button_text, "Catálogo")
        # The fields left empty still get the opening copy.
        self.assertEqual(
            company.microsite_services_title,
            MICROSITE_CONTENT_DEFAULTS["microsite_services_title"],
        )

    def test_seeding_is_idempotent(self):
        company = self.env["res.company"].create({"name": "Rerun Shop"})
        if "microsite_about_text" not in company._fields:
            self.skipTest("partner_microsite_manager is not installed.")
        company.microsite_about_text = "Edited by the merchant."
        company._seed_microsite_content_defaults()
        self.assertEqual(company.microsite_about_text, "Edited by the merchant.")

    def test_seeded_opening_hours_pass_the_format_constraint(self):
        """The default notation must survive _check_microsite_opening_hours."""
        company = self.env["res.company"].create({"name": "Hours Shop"})
        if "microsite_opening_hours" not in company._fields:
            self.skipTest("partner_microsite_manager is not installed.")
        parsed = company._get_microsite_opening_hours_lines()
        self.assertTrue(parsed, "The seeded opening hours must render as lines.")

    def test_stock_contactus_menu_is_pruned(self):
        """Not one of the 206 live merchant microsites links /contactus.

        The microsite answers contact on its own homepage, so the stock entry
        core copies onto every new website is a second, poorer door.
        """
        company = self.env["res.company"].create({"name": "Contactless Shop"})
        self.assertFalse(
            self.env["website.menu"].search(
                [
                    ("website_id", "=", company.website_id.id),
                    ("url", "=", "/contactus"),
                ]
            ),
            "The stock Contact us entry must not survive on a new microsite.",
        )

    def test_a_renamed_contact_menu_is_kept(self):
        """Pruning only ever removes the stock label; a rename is a decision."""
        company = self.env["res.company"].create({"name": "Renamed Contact Shop"})
        Menu = self.env["website.menu"]
        root = Menu.search(
            [("website_id", "=", company.website_id.id), ("parent_id", "=", False)],
            limit=1,
        )
        kept = Menu.create(
            {
                "name": "Habla con nosotros",
                "url": "/contactus",
                "parent_id": root.id,
                "website_id": company.website_id.id,
            }
        )
        company._auto_generate_microsite()
        self.assertTrue(kept.exists(), "A renamed contact entry must survive.")

    def test_new_microsite_is_born_with_the_cookies_bar(self):
        """Consent, not cosmetics: the platform sets utm cookies.

        Odoo only withholds optional cookies until consent while the bar is
        enabled; a microsite born without it sets them unasked.
        """
        company = self.env["res.company"].create({"name": "Consenting Shop"})
        if not hasattr(self.env["website.page"], "_pmm_enforce_cookie_consent"):
            self.skipTest("partner_microsite_manager is not installed.")
        self.assertTrue(
            company.website_id.cookies_bar,
            "A new microsite must ask before setting optional cookies.",
        )

    def test_a_new_microsite_is_born_without_the_local_guide_dropdown(self):
        """The platform's verticals are the zone sites' navigation, not a
        merchant's. 19.0.2.1.0 gave the dropdown to every site; the client
        ruled it out of everywhere but the commercial zone pages.
        """
        company = self.env["res.company"].create({"name": "Unguided Shop"})
        self.assertFalse(
            self.env["website.menu"].search_count(
                [
                    ("website_id", "=", company.website_id.id),
                    ("url", "in", list(LOCAL_GUIDE_URLS)),
                ]
            ),
            "a merchant microsite must not link the verticals at birth",
        )

    def test_menu_labels_are_seeded_in_every_installed_language(self):
        """ "Comercio" is the directory, not the noun.

        Left to a machine translator it comes back as Trade/Handel/Commerce,
        which is exactly what website 221 shipped with. The estate wording is
        written on creation instead.
        """
        english = self.env["res.lang"]._activate_lang("en_US")
        if not english:
            self.skipTest("en_US is not available in this database.")
        company = self.env["res.company"].create({"name": "Labelled Shop"})
        directory = self.env["website.menu"].search(
            [("website_id", "=", company.website_id.id), ("url", "=", "/comercio")],
            limit=1,
        )
        self.assertEqual(
            directory.with_context(lang="en_US").name,
            "Directory",
            "The directory entry must read Directory in English, never Trade.",
        )

    def test_seeding_writes_only_languages_that_are_installed(self):
        """Writing a language Odoo does not know raises; it must be skipped."""
        company = self.env["res.company"].create({"name": "Partial Lang Shop"})
        directory = self.env["website.menu"].search(
            [("website_id", "=", company.website_id.id), ("url", "=", "/comercio")],
            limit=1,
        )
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT name FROM website_menu WHERE id = %s", (directory.id,)
        )
        stored = self.env.cr.fetchone()[0]
        installed = {lang[0] for lang in self.env["res.lang"].get_installed()}
        self.assertTrue(
            set(stored) <= installed,
            f"Only installed languages may be written; got {sorted(stored)}.",
        )


@tagged("post_install", "-at_install")
class TestLocalGuideDropdown(TransactionCase):
    """The Guía Local dropdown is taken back from every site but the zones.

    A zone site is the website of a company carrying ``zone_company_key``,
    a field ``zone_company_ownership`` brings; that module is not a hard
    dependency here, so the cases that need a zone skip without it (as it
    is installed in the platform's real deployment, they run there).
    """

    def setUp(self):
        super().setUp()
        self.Company = self.env["res.company"]
        self.Menu = self.env["website.menu"]
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "auto"
        )

    def _website_of(self, name, zone_key=None):
        """A company with a bare website: a merchant, or a zone when keyed."""
        if zone_key and "zone_company_key" not in self.Company._fields:
            self.skipTest("zone_company_ownership is not installed here")
        company = self.Company.with_context(no_microsite_auto=True).create(
            {"name": name}
        )
        website = self.env["website"].create({"name": name, "company_id": company.id})
        if zone_key:
            company.zone_company_key = zone_key
        return website

    def _plant_local_guide(self, website, extra_url=None):
        """Build the dropdown exactly as 19.0.2.1.0 left it on every site."""
        root = self.Menu.search(
            [("website_id", "=", website.id), ("parent_id", "=", False)], limit=1
        )
        guide = self.Menu.create(
            {
                "name": "Guía Local",
                "url": "#",
                "parent_id": root.id,
                "website_id": website.id,
            }
        )
        children = [
            {"name": name, "url": url, "sequence": sequence}
            for name, url, sequence in LOCAL_GUIDE_CHILDREN
        ]
        if extra_url:
            children.append({"name": "Eventos", "url": extra_url, "sequence": 40})
        self.Menu.create(
            [dict(vals, parent_id=guide.id, website_id=website.id) for vals in children]
        )
        return guide

    def _has_local_guide(self, website):
        return bool(
            self.Menu.search_count(
                [("website_id", "=", website.id), ("url", "in", list(LOCAL_GUIDE_URLS))]
            )
        )

    def test_the_sweep_clears_the_merchant_and_spares_the_zone(self):
        zone = self._website_of("Zona Guía", zone_key="guanarteme")
        merchant = self._website_of("Comercio Guía")
        curated = self._plant_local_guide(zone)
        self._plant_local_guide(merchant)

        removed = self.Company._remove_local_guide_dropdowns(zone | merchant)

        self.assertEqual(removed, 1, "one site cleaned, one site spared")
        self.assertFalse(self._has_local_guide(merchant))
        self.assertTrue(curated.exists(), "the zone dropdown must not be touched")
        self.assertEqual(len(curated.child_id), len(LOCAL_GUIDE_CHILDREN))

    def test_the_sweep_is_idempotent(self):
        zone = self._website_of("Zona Twice", zone_key="tamaraceite")
        merchant = self._website_of("Comercio Twice")
        self._plant_local_guide(zone)
        self._plant_local_guide(merchant)
        self.Company._remove_local_guide_dropdowns(zone | merchant)
        self.assertEqual(
            self.Company._remove_local_guide_dropdowns(zone | merchant),
            0,
            "a second run must find nothing left to remove",
        )

    def test_a_dropdown_that_gained_an_entry_is_somebody_s_navigation(self):
        """Only the generated structure goes: the three vertical URLs under a
        '#' parent. One more child and it is a merchant's own menu.
        """
        self._website_of("Zona Anchor", zone_key="lomolosfrailes")
        merchant = self._website_of("Comercio Curated")
        guide = self._plant_local_guide(merchant, extra_url="/eventos-del-barrio")
        self.Company._remove_local_guide_dropdowns(merchant)
        self.assertTrue(guide.exists(), "a dropdown with its own entries is kept")

    def _migration_script(self):
        spec = importlib.util.spec_from_file_location("post_migration", MIGRATION_2_2_0)
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        return script

    def test_the_migration_sweeps_the_estate_and_spares_the_zone(self):
        """A realistic estate: several merchants and a zone site."""
        zone = self._website_of("Zona Script", zone_key="guanarteme")
        curated = self._plant_local_guide(zone)
        merchants = self.env["website"].browse()
        for index in range(3):
            merchant = self._website_of(f"Comercio Script {index}")
            self._plant_local_guide(merchant)
            merchants |= merchant

        script = self._migration_script()
        with self.assertLogs(script._logger.name, level="INFO") as capture:
            script.migrate(self.env.cr, "19.0.2.1.0")

        for merchant in merchants:
            self.assertFalse(
                self._has_local_guide(merchant),
                f"{merchant.name} must have lost the dropdown",
            )
        self.assertTrue(curated.exists(), "the migration must spare the zone site")
        self.assertEqual(len(curated.child_id), len(LOCAL_GUIDE_CHILDREN))
        removed = int(re.search(r"removed from (\d+) ", capture.output[0]).group(1))
        self.assertGreaterEqual(
            removed,
            len(merchants),
            "the migration must report what it actually removed",
        )

    def test_the_migration_finds_the_zone_sites_without_the_orm_field(self):
        """The registry is INCOMPLETE while a post-migration runs.

        This module depends only on ``website``, so ``zone_company_ownership``
        is not loaded yet and the ORM does not know ``zone_company_key``: a
        script asking the ORM for the zone companies is told there are none,
        spares every site and reports success. That is what the first cut did
        on production -- 211 sites, 0 removed. The script must resolve the
        zone companies in SQL, so the ORM probe returning nothing (simulated
        here) may not change the outcome.
        """
        zone = self._website_of("Zona Sin ORM", zone_key="tamaraceite")
        merchant = self._website_of("Comercio Sin ORM")
        curated = self._plant_local_guide(zone)
        self._plant_local_guide(merchant)

        script = self._migration_script()
        with patch.object(
            type(self.Company), "_zone_companies_or_none", lambda self: None
        ):
            script.migrate(self.env.cr, "19.0.2.1.0")

        self.assertFalse(
            self._has_local_guide(merchant),
            "the sweep must run on the merchant even with the ORM probe blind",
        )
        self.assertTrue(curated.exists(), "the zone site must still be spared")
        self.assertEqual(len(curated.child_id), len(LOCAL_GUIDE_CHILDREN))

    def test_the_migration_removes_nothing_when_no_zone_can_be_told_apart(self):
        """No keyed company: spare everything rather than strip the zones."""
        merchant = self._website_of("Comercio Sin Zona")
        self._plant_local_guide(merchant)
        script = self._migration_script()
        with patch.object(script, "_zone_company_ids", lambda cr: []):
            script.migrate(self.env.cr, "19.0.2.1.0")
        self.assertTrue(
            self._has_local_guide(merchant),
            "with no zone known the sweep must not touch a thing",
        )


@tagged("post_install", "-at_install")
class TestMicrositeSubdomain(TransactionCase):
    """The subdomain is named by a person, before the site exists.

    DNS here is manual: no registrar API, and a wildcard certificate renewed
    by hand. A website born on a hostname nobody registered is a dead link
    with a merchant attached, so "ask" is the default and this is what it
    means.
    """

    def setUp(self):
        super().setUp()
        self.Company = self.env["res.company"]
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "ask"
        )
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.domain_suffix", ".canariasconectada.es"
        )

    def test_a_company_without_a_subdomain_gets_no_website(self):
        company = self.Company.create({"name": "Unnamed Shop"})
        self.assertFalse(
            company.website_id,
            "In ask mode nothing may be published until a subdomain is named.",
        )

    def test_a_subdomain_given_on_create_provisions_the_site(self):
        company = self.Company.create(
            {"name": "Named Shop", "microsite_subdomain": "namedshop"}
        )
        self.assertEqual(
            company.website_id.domain,
            "https://namedshop.canariasconectada.es",
            "A caller who answered the question must not be asked again.",
        )

    def test_a_mixed_batch_provisions_only_the_named_ones(self):
        companies = self.Company.create(
            [
                {"name": "Batch Named", "microsite_subdomain": "batchnamed"},
                {"name": "Batch Unnamed"},
            ]
        )
        self.assertEqual(
            len(companies), 2, "create must return every company it was given."
        )
        self.assertTrue(companies[0].website_id)
        self.assertFalse(companies[1].website_id)

    def test_the_wizard_names_the_subdomain_and_builds_the_site(self):
        company = self.Company.create({"name": "Wizard Shop"})
        wizard = (
            self.env["microsite.creation.wizard"]
            .with_context(active_id=company.id)
            .create({"company_id": company.id, "subdomain": "wizardshop"})
        )
        wizard.action_create_microsite()
        self.assertEqual(
            company.website_id.domain, "https://wizardshop.canariasconectada.es"
        )

    def test_the_wizard_suggests_a_subdomain_without_deciding_it(self):
        company = self.Company.create({"name": "Suggested Shop"})
        defaults = (
            self.env["microsite.creation.wizard"]
            .with_context(active_id=company.id)
            .default_get(["company_id", "subdomain", "domain_suffix"])
        )
        self.assertEqual(defaults["subdomain"], "suggestedshop")
        self.assertEqual(defaults["company_id"], company.id)

    def test_the_wizard_shows_the_address_to_point_dns_at(self):
        company = self.Company.create({"name": "Preview Shop"})
        wizard = (
            self.env["microsite.creation.wizard"]
            .with_context(active_id=company.id)
            .create({"company_id": company.id, "subdomain": "previewshop"})
        )
        self.assertEqual(
            wizard.address,
            "https://previewshop.canariasconectada.es",
            "The operator must read the exact hostname before publishing.",
        )

    def test_the_wizard_refuses_a_company_that_already_has_a_site(self):
        company = self.Company.create(
            {"name": "Twice Shop", "microsite_subdomain": "twiceshop"}
        )
        wizard = (
            self.env["microsite.creation.wizard"]
            .with_context(active_id=company.id)
            .create({"company_id": company.id, "subdomain": "twiceshop2"})
        )
        with self.assertRaises(UserError):
            wizard.action_create_microsite()

    def test_a_malformed_subdomain_is_rejected(self):
        for bad in ("Neveri", "neveri.canariasconectada.es", "ne veri", "-neveri"):
            with self.subTest(subdomain=bad), self.assertRaises(ValidationError):
                self.Company.create({"name": f"Bad {bad}", "microsite_subdomain": bad})

    def test_two_companies_cannot_share_a_subdomain(self):
        self.Company.create({"name": "First Shop", "microsite_subdomain": "shared"})
        with self.assertRaises(ValidationError):
            self.Company.create(
                {"name": "Second Shop", "microsite_subdomain": "shared"}
            )

    def test_auto_mode_writes_the_derived_subdomain_back(self):
        """The record must say where the site answers, not just the regex."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "auto"
        )
        company = self.Company.create({"name": "Derived Shop"})
        self.assertEqual(company.microsite_subdomain, "derivedshop")
        self.assertEqual(
            company.microsite_address, "https://derivedshop.canariasconectada.es"
        )

    def test_auto_mode_does_not_lose_the_second_shop_of_a_clashing_name(self):
        """Company names are unique; the subdomains derived from them are not.

        Accents and punctuation are stripped on the way to a DNS label, so
        two genuinely different shops collide -- and the second one must not
        be the one left without a website.
        """
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "auto"
        )
        first = self.Company.create({"name": "Panadería Luz"})
        second = self.Company.create({"name": "Panaderia Luz!"})
        self.assertEqual(first.microsite_subdomain, "panaderialuz")
        self.assertEqual(second.microsite_subdomain, "panaderialuz-2")
        self.assertTrue(second.website_id, "The clash must not cost it its site.")

    def test_an_unknown_mode_reads_as_ask(self):
        """A typo must fail towards being asked, never towards publishing."""
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "atuo"
        )
        company = self.Company.create({"name": "Typo Shop"})
        self.assertFalse(company.website_id)
