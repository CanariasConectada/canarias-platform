# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Which neighbourhood a portal lists: from the declared data, not the URL.

``/comercio`` used to decide by looking for "guanarteme", "tamaraceite" or
"frailes" INSIDE the website domain. Renaming the domain, adding a ``www.``,
putting up a staging copy or opening a new neighbourhood all fell through to
the global value, and the neighbourhood portal started listing EVERY business
on the platform with nothing to explain it.

The zone now comes from ``website.marketplace_zone`` — declared on the website
itself, already set on the three portals, immune to the URL. The domain
heuristic stays as a fallback and is left untouched, so the ~180 business
microsites (which declare no zone) resolve exactly as they do today.

The company zone is deliberately not consulted: on the live database the three
portals belong to companies in ``canarias`` (so it would fix nothing) while the
business microsites do carry a real zone (so it would silently shrink 83% of
the live sites to their own street).
"""
from unittest.mock import patch

from odoo.tests import TransactionCase, tagged

from odoo.addons.website_directory.controllers.main import WebsiteDirectory

LOGGER = "odoo.addons.website_directory.controllers.main"


@tagged("post_install", "-at_install")
class TestZoneResolution(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, no_microsite_auto=True))
        cls.controller = WebsiteDirectory()
        cls.company = cls.env["res.company"].create({"name": "WDZ Zone Shop"})
        # website_sale_marketplace IS installed in the target deployment (it
        # owns marketplace_zone on the three portals), so these guards must
        # never fire there. They only keep the suite green on a slimmer
        # database, since website_directory does not depend on that module.
        cls.marketplace_installed = "marketplace_zone" in cls.env["website"]._fields
        cls.company_zone_installed = "commercial_zone" in cls.env["res.company"]._fields

    def _make_website(self, domain, **extra):
        """Create a website without running the marketplace product backfill.

        ``website_sale_marketplace`` hooks ``create``/``write`` to link the
        whole catalogue to a marketplace company. That is irrelevant to zone
        resolution (which never reads ``is_marketplace``) and is documented in
        that module as heavy and prone to blowing up on delivery carriers, so
        it is stubbed out when the module is around.
        """
        vals = {
            "name": "WDZ Website",
            "domain": domain,
            "company_id": self.company.id,
        }
        vals.update(extra)
        website_cls = type(self.env["website"])
        if not hasattr(website_cls, "_sync_marketplace_products"):
            return self.env["website"].create(vals)
        with patch.object(website_cls, "_sync_marketplace_products", lambda self: None):
            return self.env["website"].create(vals)

    def _set_marketplace_zone(self, website, raw):
        """Store a raw zone value on the website column.

        Written in SQL on purpose: ``marketplace_zone`` takes its selection
        from ``res.company.commercial_zone`` (``res_company_zone``), so the ORM
        would reject both a legacy spelling and any value at all on a database
        without that module. The column is exactly what production holds and
        exactly what the controller reads.
        """
        self.env.cr.execute(
            "UPDATE website SET marketplace_zone = %s WHERE id = %s",
            (raw, website.id),
        )
        website.invalidate_recordset(["marketplace_zone"])

    # ------------------------------------------------------------------
    # 1. The declared zone wins
    # ------------------------------------------------------------------
    def test_marketplace_zone_wins_over_contradicting_domain(self):
        """The regression: a renamed portal still lists its own barrio."""
        if not self.marketplace_installed:
            self.skipTest("website_sale_marketplace is not installed on this database")
        # A domain that only *looks* like the Guanarteme portal: the real one
        # exists on any copy of production, and ``website_domain_unique``
        # (core, website/models/website.py) would abort the fixture.
        website = self._make_website("https://guanarteme.example.com")
        self._set_marketplace_zone(website, "tamaraceite")

        self.assertEqual(self.controller._get_zone_from_website(website), "tamaraceite")

    def test_marketplace_zone_wins_over_unrecognised_domain(self):
        """A staging URL no longer turns a zone portal into the platform."""
        if not self.marketplace_installed:
            self.skipTest("website_sale_marketplace is not installed on this database")
        website = self._make_website("https://staging-portal.example.com")
        self._set_marketplace_zone(website, "lomolosfrailes")

        self.assertEqual(
            self.controller._get_zone_from_website(website), "lomolosfrailes"
        )

    def test_legacy_alias_in_marketplace_zone_is_normalised(self):
        """Migrated rows spell it ``lomo_los_frailes``; entries do not."""
        if not self.marketplace_installed:
            self.skipTest("website_sale_marketplace is not installed on this database")
        website = self._make_website("https://portal.example.com")
        self._set_marketplace_zone(website, "lomo_los_frailes")

        self.assertEqual(
            self.controller._get_zone_from_website(website), "lomolosfrailes"
        )

    # ------------------------------------------------------------------
    # 2. Silence on every path a real request takes
    # ------------------------------------------------------------------
    def test_marketplace_without_zone_is_global_and_silent(self):
        """Website 1's shape: global marketplace, empty zone, correct as is.

        Empty means "the whole platform" for the main portal, so there is
        nothing to warn about — and ``/comercio`` is a high-traffic page on a
        deployment with no log rotation, so a per-request line is a defect in
        itself.
        """
        if not self.marketplace_installed:
            self.skipTest("website_sale_marketplace is not installed on this database")
        # Same shape as the main portal, but not its real domain: that one
        # already exists on a production copy and the fixture would collide.
        website = self._make_website("https://plataforma.example.com")
        self._set_marketplace_zone(website, None)

        with self.assertNoLogs(LOGGER, level="DEBUG"):
            zone = self.controller._get_zone_from_website(website)

        self.assertEqual(zone, "canarias")

    def test_domain_heuristic_still_resolves_and_is_silent(self):
        """The fallback is untouched, and it does not talk either."""
        website = self._make_website("https://www.guanarteme.example.com")

        with self.assertNoLogs(LOGGER, level="DEBUG"):
            zone = self.controller._get_zone_from_website(website)

        self.assertEqual(zone, "guanarteme")

    # ------------------------------------------------------------------
    # 3. Business microsites keep behaving exactly as today
    # ------------------------------------------------------------------
    def test_business_microsite_is_unaffected(self):
        """No declared zone: same answer as the domain heuristic alone."""
        website = self._make_website("https://panaderia-siony.example.com")

        zone = self.controller._get_zone_from_website(website)

        self.assertIsNone(self.controller._get_domain_zone(website))
        self.assertEqual(zone, "canarias")

    def test_company_zone_does_not_narrow_a_microsite(self):
        """The 181 microsites with a real company zone still list globally.

        This is the behaviour the product owner asked to preserve: the company
        zone must not reach the directory listing of a business microsite.
        """
        if not self.company_zone_installed:
            self.skipTest("res_company_zone is not installed on this database")
        self.company.commercial_zone = "guanarteme"
        website = self._make_website("https://panaderia-siony.example.com")

        self.assertEqual(self.controller._get_zone_from_website(website), "canarias")

    # ------------------------------------------------------------------
    # 4. Broken and empty state
    # ------------------------------------------------------------------
    def test_unknown_marketplace_zone_warns_and_falls_back(self):
        """Only genuinely broken data talks, and it cannot be reached twice.

        The ORM cannot store a value outside the selection, so this needs a bad
        migration or a manual UPDATE — the one case worth a line in the log.
        """
        if not self.marketplace_installed:
            self.skipTest("website_sale_marketplace is not installed on this database")
        website = self._make_website("https://portal.example.com")
        self._set_marketplace_zone(website, "barrio_inventado")

        with self.assertLogs(LOGGER, level="WARNING") as logs:
            zone = self.controller._get_zone_from_website(website)

        self.assertEqual(zone, "canarias")
        self.assertIn("unknown marketplace zone", "".join(logs.output))

    def test_unrecognised_domain_is_global(self):
        website = self._make_website("https://staging-guana.example.com")

        self.assertEqual(self.controller._get_zone_from_website(website), "canarias")

    def test_no_website_is_global(self):
        """Nothing to resolve, and nothing to crash on."""
        self.assertEqual(
            self.controller._get_zone_from_website(self.env["website"]),
            "canarias",
        )

    def test_empty_domain_is_not_a_crash(self):
        """A website with no domain yet (fresh setup) must not explode."""
        website = self._make_website(False)

        self.assertEqual(self.controller._get_zone_from_website(website), "canarias")
