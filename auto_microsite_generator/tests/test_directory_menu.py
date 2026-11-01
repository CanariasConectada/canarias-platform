# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
import re
from pathlib import Path
from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from ..models.res_company import DIRECTORY_MENU_URL, ZONE_MENU_CHILDREN

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"
MODEL_LOGGER = "odoo.addons.auto_microsite_generator.models.res_company"


@tagged("post_install", "-at_install")
class TestMicrositeDirectoryMenu(TransactionCase):
    """A merchant microsite does not link the directory from its top menu.

    Once inside a shop the visitor is not invited out to the list of all the
    other shops; the "Zonas Comerciales" dropdown is the way out. The portal
    and the zone sites keep their ``/comercio`` entry, and the route itself
    is nobody's business here.
    """

    def setUp(self):
        super().setUp()
        self.Company = self.env["res.company"]
        self.Menu = self.env["website.menu"]
        self.env["ir.config_parameter"].sudo().set_param(
            "auto_microsite_generator.subdomain_mode", "auto"
        )

    # ------------------------------------------------------------------
    # Fixtures
    # ------------------------------------------------------------------
    def _website_of(self, name):
        """A company with a bare website, its core menus and nothing else."""
        company = self.Company.with_context(no_microsite_auto=True).create(
            {"name": name}
        )
        return self.env["website"].create({"name": name, "company_id": company.id})

    def _root(self, website):
        return self.Menu.search(
            [("website_id", "=", website.id), ("parent_id", "=", False)], limit=1
        )

    def _plant_directory(self, website, parent=None):
        """The entry exactly as the generator and 19.0.2.1.0 left it."""
        return self.Menu.create(
            {
                "name": "Comercio",
                "url": DIRECTORY_MENU_URL,
                "parent_id": (parent or self._root(website)).id,
                "sequence": 30,
                "website_id": website.id,
            }
        )

    def _directory_entries(self, website):
        return self.Menu.search(
            [("website_id", "=", website.id), ("url", "=", DIRECTORY_MENU_URL)]
        )

    def _stored_names(self, website):
        """The raw jsonb ``name`` of every menu of ``website``, by id."""
        self.env.flush_all()
        self.env.cr.execute(
            "SELECT id, name FROM website_menu WHERE website_id = %s", (website.id,)
        )
        return dict(self.env.cr.fetchall())

    def _migration_script(self, version="19.0.2.3.0"):
        spec = importlib.util.spec_from_file_location(
            "post_migration", MIGRATIONS / version / "post-migration.py"
        )
        script = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(script)
        return script

    def _make_aggregated(self, website):
        """Flag ``website`` as an aggregated shop, the way the sweep reads it.

        Straight into the column: through the ORM the flag backfills a whole
        marketplace (pickup carrier, a thousand products).
        """
        if "is_marketplace" not in self.env["website"]._fields:
            self.skipTest("website_sale_marketplace is not installed here")
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE website SET is_marketplace = TRUE WHERE id = %s", (website.id,)
        )
        website.invalidate_recordset(["is_marketplace"])

    def _spared_reasons(self, report, website):
        return next(
            (
                reasons
                for site_id, *_company, reasons in report["spared"]
                if site_id == website.id
            ),
            None,
        )

    def _keyed_zone(self, name, zone_key):
        """A zone site the way production tells one: ``zone_company_key``."""
        if "zone_company_key" not in self.Company._fields:
            self.skipTest("zone_company_ownership is not installed here")
        website = self._website_of(name)
        website.company_id.zone_company_key = zone_key
        return website

    # ------------------------------------------------------------------
    # The generator
    # ------------------------------------------------------------------
    def test_a_new_microsite_is_born_without_the_directory_entry(self):
        company = self.Company.create({"name": "Undirected Shop"})
        website = company.website_id
        top = self.Menu.search(
            [
                ("website_id", "=", website.id),
                ("parent_id", "=", self._root(website).id),
            ]
        )
        urls = top.mapped("url")
        self.assertIn("/", urls, "Home must still be there")
        self.assertIn("/shop", urls, "Shop must still be there")
        zones = top.filtered(lambda menu: menu.url == "#" and menu.child_id)
        self.assertEqual(len(zones), 1, "the zone dropdown is the way out")
        self.assertEqual(
            zones.child_id.sorted("sequence").mapped("url"),
            [url for _name, url, _sequence in ZONE_MENU_CHILDREN],
        )
        self.assertFalse(
            self._directory_entries(website),
            "a merchant microsite must not link the directory at birth",
        )

    def test_a_second_generation_pass_does_not_bring_the_entry_back(self):
        company = self.Company.create({"name": "Still Undirected Shop"})
        company._auto_generate_microsite()
        self.assertFalse(self._directory_entries(company.website_id))

    # ------------------------------------------------------------------
    # The sweep
    # ------------------------------------------------------------------
    def test_the_sweep_clears_the_merchant_and_spares_the_platform_sites(self):
        zone = self._website_of("Barrio Directorio")
        named = self._website_of("Zona Comercial Directorio")
        portal = self._website_of("Canarias Conectada Directorio")
        merchant = self._website_of("Comercio Directorio")
        kept = (
            self._plant_directory(zone)
            | self._plant_directory(named)
            | self._plant_directory(portal)
        )
        self._plant_directory(merchant)
        names_before = self._stored_names(merchant)

        report = self.Company._remove_microsite_directory_menus(
            zone | named | portal | merchant, zone_companies=zone.company_id
        )

        self.assertEqual(report["deleted"], [merchant.id])
        self.assertEqual(self._spared_reasons(report, zone), ["zone_company"])
        self.assertEqual(self._spared_reasons(report, named), ["protected_name"])
        self.assertEqual(self._spared_reasons(report, portal), ["protected_name"])
        self.assertEqual(
            (report["spared"][0][1], report["spared"][0][2]),
            (zone.company_id.id, zone.company_id.name),
            "a spared site is reported with its company, for the run log",
        )
        self.assertFalse(self._directory_entries(merchant))
        self.assertEqual(
            kept.exists(), kept, "zone, zone-named and portal-named sites keep theirs"
        )
        names_after = self._stored_names(merchant)
        self.assertEqual(
            names_after,
            {
                menu_id: name
                for menu_id, name in names_before.items()
                if menu_id in names_after
            },
            "no other menu's translations may be touched",
        )
        self.assertEqual(len(names_after), len(names_before) - 1)

    def test_the_sweep_spares_an_aggregated_shop(self):
        """``is_marketplace`` alone is enough: the portal has no zone key."""
        zone = self._website_of("Barrio Agregado")
        aggregated = self._website_of("Escaparate Agregado")
        self._make_aggregated(aggregated)
        entry = self._plant_directory(aggregated)

        report = self.Company._remove_microsite_directory_menus(
            aggregated, zone_companies=zone.company_id
        )

        self.assertTrue(entry.exists())
        self.assertFalse(report["deleted"])
        self.assertEqual(
            self._spared_reasons(report, aggregated),
            ["marketplace_site", "marketplace_company"],
        )

    def test_the_second_site_of_a_platform_company_is_spared_whatever_its_name(self):
        """Production's topology: company 1 owns the portal (website 1, an
        aggregated shop) AND the Admin Portal (website 198, a plain site).
        Nothing on 198 itself says "platform"; its company owning an
        aggregated shop does, and that must hold with no help from the name
        guard -- a company can be renamed, its websites cannot change hands
        by accident.
        """
        zone = self._website_of("Barrio Estructura")
        portal = self._website_of("Plataforma Estructura")
        self._make_aggregated(portal)
        admin = self.env["website"].create(
            {"name": "Admin Estructura", "company_id": portal.company_id.id}
        )
        merchant = self._website_of("Comercio Estructura")
        kept = self._plant_directory(portal) | self._plant_directory(admin)
        self._plant_directory(merchant)
        self.assertFalse(
            portal.company_id._microsite_is_protected(),
            "the fixture must match no name pattern, or it proves nothing",
        )

        report = self.Company._remove_microsite_directory_menus(
            portal | admin | merchant, zone_companies=zone.company_id
        )

        self.assertEqual(kept.exists(), kept, "both sites of the company keep theirs")
        self.assertEqual(self._spared_reasons(report, admin), ["marketplace_company"])
        self.assertEqual(report["deleted"], [merchant.id])

        # Renamed from a protected name to a neutral one: still spared.
        portal.company_id.name = "Canarias Conectada Estructura"
        self.assertTrue(portal.company_id._microsite_is_protected())
        portal.company_id.name = "Renamed Holding Estructura"
        report = self.Company._remove_microsite_directory_menus(
            portal | admin, zone_companies=zone.company_id
        )
        self.assertEqual(kept.exists(), kept, "a rename must not expose either site")
        self.assertEqual(self._spared_reasons(report, admin), ["marketplace_company"])

    def test_a_merchant_named_like_a_zone_keeps_its_entry(self):
        """INTENDED, and harmless: the name guard is free text and errs on
        the safe side. A shop called "Zona Comercial Pepe Shop" is nothing
        but a merchant, yet it matches the pattern the generator protects,
        so its entry stays. The cost is one menu entry nobody minds (and no
        production merchant matches a pattern today); the opposite mistake
        would strip the portal. It is reported as spared BY NAME ONLY, which
        is how such a site is told apart in the run log.
        """
        zone = self._website_of("Barrio Homónimo")
        lookalike = self._website_of("Zona Comercial Pepe Shop")
        entry = self._plant_directory(lookalike)

        report = self.Company._remove_microsite_directory_menus(
            lookalike, zone_companies=zone.company_id
        )

        self.assertTrue(entry.exists(), "a name lookalike is spared, by design")
        self.assertEqual(self._spared_reasons(report, lookalike), ["protected_name"])
        self.assertFalse(report["deleted"])

    def test_the_sweep_is_idempotent(self):
        zone = self._website_of("Barrio Twice")
        merchant = self._website_of("Comercio Twice")
        self._plant_directory(zone)
        self._plant_directory(merchant)
        self.Company._remove_microsite_directory_menus(
            zone | merchant, zone_companies=zone.company_id
        )
        report = self.Company._remove_microsite_directory_menus(
            zone | merchant, zone_companies=zone.company_id
        )
        self.assertFalse(report["deleted"], "a second run finds nothing left")
        self.assertEqual(len(self._directory_entries(zone)), 1)

    def test_an_entry_with_children_is_somebody_s_navigation(self):
        """Core turns the url of a menu that gains children into ``#``, so
        the ORM cannot build this shape; rows written in SQL (the data
        migration's way) can carry it, and the guard is for them.
        """
        zone = self._website_of("Barrio Dropdown")
        merchant = self._website_of("Comercio Dropdown")
        entry = self._plant_directory(merchant)
        self.Menu.create(
            {
                "name": "Nearby shops",
                "url": "/comercio?zona=cerca",
                "parent_id": entry.id,
                "website_id": merchant.id,
            }
        )
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE website_menu SET url = %s WHERE id = %s",
            (DIRECTORY_MENU_URL, entry.id),
        )
        entry.invalidate_recordset(["url"])
        report = self.Company._remove_microsite_directory_menus(
            merchant, zone_companies=zone.company_id
        )
        self.assertTrue(entry.exists(), "an entry turned into a dropdown is kept")
        self.assertEqual(len(entry.child_id), 1)
        self.assertFalse(report["deleted"])
        self.assertEqual(
            report["kept"],
            [
                (
                    merchant.id,
                    merchant.company_id.id,
                    merchant.company_id.name,
                    entry.id,
                    "has_children",
                )
            ],
            "what is kept must be reported with its site and its reason",
        )

    def test_an_entry_moved_under_a_dropdown_is_kept(self):
        zone = self._website_of("Barrio Nested")
        merchant = self._website_of("Comercio Nested")
        dropdown = self.Menu.create(
            {
                "name": "More",
                "url": "#",
                "parent_id": self._root(merchant).id,
                "website_id": merchant.id,
            }
        )
        entry = self._plant_directory(merchant, parent=dropdown)
        report = self.Company._remove_microsite_directory_menus(
            merchant, zone_companies=zone.company_id
        )
        self.assertTrue(entry.exists(), "only a top-level entry is the generated one")
        self.assertEqual(
            [kept[-2:] for kept in report["kept"]], [(entry.id, "not_top_level")]
        )

    def test_a_re_pointed_entry_is_not_even_seen(self):
        zone = self._website_of("Barrio Repointed")
        merchant = self._website_of("Comercio Repointed")
        entry = self._plant_directory(merchant)
        entry.url = "/comercio/mi-barrio"
        report = self.Company._remove_microsite_directory_menus(
            merchant, zone_companies=zone.company_id
        )
        self.assertTrue(entry.exists())
        self.assertFalse(any(report.values()))

    def test_the_migration_anchor_of_a_deleted_entry_goes_with_it(self):
        """``canarias_mig.menu_*`` rows must not outlive their menu."""
        zone = self._website_of("Barrio Anchor")
        merchant = self._website_of("Comercio Anchor")
        entry = self._plant_directory(merchant)
        anchor = self.env["ir.model.data"].create(
            {
                "module": "canarias_mig",
                "name": f"menu_{entry.id}",
                "model": "website.menu",
                "res_id": entry.id,
                "noupdate": True,
            }
        )
        self.Company._remove_microsite_directory_menus(
            merchant, zone_companies=zone.company_id
        )
        self.assertFalse(entry.exists())
        self.assertFalse(anchor.exists(), "the external id must go with the menu")

    def test_nothing_goes_when_no_zone_can_be_told_apart(self):
        merchant = self._website_of("Comercio Sin Zona")
        entry = self._plant_directory(merchant)
        with patch.object(
            type(self.Company), "_zone_companies_or_none", lambda self: None
        ), self.assertLogs(MODEL_LOGGER, level="WARNING"):
            report = self.Company._remove_microsite_directory_menus(merchant)
        self.assertTrue(entry.exists())
        self.assertFalse(any(report.values()))

    # ------------------------------------------------------------------
    # The 19.0.2.3.0 script
    # ------------------------------------------------------------------
    def test_the_migration_sweeps_the_estate_and_spares_the_zone(self):
        zone = self._keyed_zone("Barrio Script", "guanarteme")
        curated = self._plant_directory(zone)
        merchants = self.env["website"].browse()
        for index in range(3):
            merchant = self._website_of(f"Comercio Script {index}")
            self._plant_directory(merchant)
            merchants |= merchant

        script = self._migration_script()
        with self.assertLogs(script._logger.name, level="INFO") as capture:
            script.migrate(self.env.cr, "19.0.2.2.0")

        for merchant in merchants:
            self.assertFalse(
                self._directory_entries(merchant),
                f"{merchant.name} must have lost the entry",
            )
        self.assertTrue(curated.exists(), "the migration must spare the zone site")
        summary = next(line for line in capture.output if "deleted from" in line)
        deleted = int(re.search(r"deleted from (\d+) ", summary).group(1))
        self.assertGreaterEqual(
            deleted, len(merchants), "the migration must report what it deleted"
        )
        # The one-off production run is diffed against these lines.
        ids_line = next(line for line in capture.output if "website ids:" in line)
        logged_ids = {
            int(found) for found in re.findall(r"\d+", ids_line.split("ids:")[1])
        }
        self.assertEqual(len(logged_ids), deleted)
        self.assertTrue(set(merchants.ids) <= logged_ids)
        spared_line = next(
            line for line in capture.output if f"SPARED on website {zone.id} " in line
        )
        self.assertIn(f"(company {zone.company_id.id}, Barrio Script)", spared_line)
        self.assertIn("zone_company", spared_line)

        with self.assertLogs(script._logger.name, level="INFO") as capture:
            script.migrate(self.env.cr, "19.0.2.2.0")
        summary = next(line for line in capture.output if "deleted from" in line)
        self.assertIn("deleted from 0 ", summary, "a second run is a no-op")

    def test_the_migration_finds_the_zone_sites_without_the_orm_field(self):
        """The registry is incomplete while a post-migration runs, and the
        ORM probe for the zone companies answers nothing there. Simulated
        here, both halves are shown under the SAME blind probe: the model
        method left to it refuses to touch a thing, and the script, which
        resolves the zone companies in SQL and hands them over, still does
        its job.
        """
        zone = self._keyed_zone("Barrio Sin ORM", "tamaraceite")
        merchant = self._website_of("Comercio Sin ORM")
        curated = self._plant_directory(zone)
        entry = self._plant_directory(merchant)

        script = self._migration_script()
        with patch.object(
            type(self.Company), "_zone_companies_or_none", lambda self: None
        ):
            with self.assertLogs(MODEL_LOGGER, level="WARNING"):
                report = self.Company._remove_microsite_directory_menus(zone | merchant)
            self.assertFalse(any(report.values()), "blind, the method must refuse")
            self.assertTrue(entry.exists())

            script.migrate(self.env.cr, "19.0.2.2.0")

        self.assertFalse(entry.exists(), "the script must not depend on the probe")
        self.assertTrue(curated.exists(), "the zone site must still be spared")

    def test_upgrading_from_before_2_1_0_restores_then_removes(self):
        """A database older than 19.0.2.1.0 runs BOTH scripts, in version
        order, on one cursor: 19.0.2.1.0 restores ``/comercio`` wherever it
        is missing, merchants included, and 19.0.2.3.0 must leave it on the
        platform sites alone.
        """
        zone = self._keyed_zone("Barrio Orden", "lomolosfrailes")
        portal = self._website_of("Plataforma Orden")
        self._make_aggregated(portal)
        merchant = self._website_of("Comercio Orden")
        for website in zone | portal | merchant:
            self.assertFalse(self._directory_entries(website), "born without it")

        self._migration_script("19.0.2.1.0").migrate(self.env.cr, "19.0.2.0.0")
        for website in zone | portal | merchant:
            self.assertEqual(
                len(self._directory_entries(website)),
                1,
                f"19.0.2.1.0 restores the entry on {website.name}",
            )

        self._migration_script().migrate(self.env.cr, "19.0.2.0.0")
        self.assertFalse(
            self._directory_entries(merchant), "the merchant ends without the entry"
        )
        self.assertEqual(len(self._directory_entries(zone)), 1, "the zone keeps it")
        self.assertEqual(len(self._directory_entries(portal)), 1, "the portal keeps it")

    def test_the_migration_does_nothing_on_a_fresh_install(self):
        merchant = self._website_of("Comercio Fresh Install")
        entry = self._plant_directory(merchant)
        self._migration_script().migrate(self.env.cr, None)
        self.assertTrue(entry.exists())
