# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Zone path + filters: the two must combine, and stay on the same host.

Reported 2026-08-26: picking a zone in the sidebar threw away the search,
the category and every bridge filter (the option values were bare
``/comercio/zona/<key>``), and once on a zone path, the first AJAX refresh
silently widened the listing to the whole archipelago (the AJAX endpoint
only knew the website's zone, and ``pushState`` rewrote the address to a
bare ``/comercio``).
"""

import re
from html import unescape
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.website_directory.controllers.main import WebsiteDirectory

ZONE_A = "guanarteme"
ZONE_B = "tamaraceite"
# browser_js wants a strict boolean, not the matched element.
READY = (
    "!!(document.getElementById('wd_data')"
    " && document.querySelector('a.wd-filter-chip-x'))"
)


def _unlang(url):
    """Drop the ``/<lang>/`` prefix the website layer adds to every href."""
    return re.sub(r"^/[a-z]{2}(?:_[A-Z]{2})?(?=/)", "", url)


class ZoneFixtures:
    """Two shops in two zones under one leaf category."""

    @classmethod
    def _setup_zone_fixtures(cls):
        Category = cls.env["res.company.category"]
        cls.root_category = Category.create({"name": "WDZ Root", "type": "view"})
        cls.leaf = Category.create(
            {"name": "WDZ Leaf", "type": "normal", "parent_id": cls.root_category.id}
        )
        Company = cls.env["res.company"]
        cls.company_a = Company.create(
            {"name": "WDZ Alpha Guanarteme", "category_id": cls.leaf.id}
        )
        cls.company_b = Company.create(
            {"name": "WDZ Beta Tamaraceite", "category_id": cls.leaf.id}
        )
        companies = cls.company_a | cls.company_b
        companies._sync_to_directory_entry()
        companies.directory_sync_pending = False
        Entry = cls.env["website.directory.entry"].sudo()
        cls.entry_a = Entry.search([("company_id", "=", cls.company_a.id)])
        cls.entry_b = Entry.search([("company_id", "=", cls.company_b.id)])
        # The sync only sets the zone on creation and preserves it after,
        # so the fixtures own their zone regardless of any zone module.
        cls.entry_a.zone = ZONE_A
        cls.entry_b.zone = ZONE_B
        cls.zone_page = f"/comercio/zona/{ZONE_A}"


@tagged("post_install", "-at_install")
class TestZoneFilters(ZoneFixtures, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_zone_fixtures()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _zone_option_values(self, html):
        select = re.search(
            r'<select[^>]*id="wd_zone_select".*?</select>', html, re.S
        ).group(0)
        return [
            unescape(value)
            for value in re.findall(r'<option[^>]*value="([^"]*)"', select)
        ]

    def _attr(self, html, element_id, attr):
        match = re.search(r'<[a-z]+[^>]*id="%s"[^>]*>' % element_id, html)
        self.assertIsNotNone(match, f"#{element_id} not rendered")
        value = re.search(r'%s="([^"]*)"' % attr, match.group(0))
        self.assertIsNotNone(value, f"#{element_id} has no {attr}")
        return _unlang(unescape(value.group(1)))

    def _category_chip_hrefs(self, html):
        """The href of every category "x" chip (top bar), lang prefix removed.

        Attribute order is QWeb's (static ``class`` first, ``t-att-href``
        last), and the website layer prefixes hrefs with the language code.
        """
        chips = re.findall(
            r'<a[^>]*class="wd-filter-link wd-filter-chip-x"[^>]*>', html
        )
        return [
            _unlang(unescape(re.search(r'href="([^"]*)"', chip).group(1)))
            for chip in chips
        ]

    # ------------------------------------------------------------------
    # Zone select carries the active filters
    # ------------------------------------------------------------------
    def test_zone_options_carry_category_and_search(self):
        response = self.url_open(f"{self.zone_page}?category={self.leaf.id}&search=WDZ")
        self.assertEqual(response.status_code, 200)
        values = self._zone_option_values(response.text)
        expected_query = f"?category={self.leaf.id}&search=WDZ"
        self.assertIn(f"/comercio{expected_query}", values, "'All zones' option")
        self.assertIn(f"/comercio/zona/{ZONE_B}{expected_query}", values)
        self.assertIn(f"{self.zone_page}{expected_query}", values)
        for value in values:
            self.assertNotIn("zone=", value, "the zone travels in the path only")

    def test_zone_options_carry_bridge_params(self):
        """Whatever a bridge module put in the query string survives too."""
        response = self.url_open("/comercio?facility=1,2&certification=silver")
        self.assertEqual(response.status_code, 200)
        values = self._zone_option_values(response.text)
        target = [
            value for value in values if value.startswith(f"/comercio/zona/{ZONE_B}")
        ]
        self.assertEqual(len(target), 1)
        self.assertIn("facility=1%2C2", target[0])
        self.assertIn("certification=silver", target[0])

    def test_zone_page_exposes_base_url_and_zone(self):
        response = self.url_open(f"{self.zone_page}?search=WDZ")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._attr(response.text, "wd_data", "data-base-url"), self.zone_page
        )
        self.assertEqual(self._attr(response.text, "wd_data", "data-zone"), ZONE_A)
        # No-JS fallback: both forms post back onto the zone path.
        self.assertEqual(
            self._attr(response.text, "wd_search_form", "action"), self.zone_page
        )
        self.assertEqual(
            self._attr(response.text, "wd_category_form", "action"), self.zone_page
        )
        response = self.url_open("/comercio")
        self.assertEqual(
            self._attr(response.text, "wd_data", "data-base-url"), "/comercio"
        )

    # ------------------------------------------------------------------
    # Category chip "x": keeps the zone path and the other filters
    # ------------------------------------------------------------------
    def test_category_clear_chip_keeps_zone_path_and_search(self):
        response = self.url_open(f"{self.zone_page}?category={self.leaf.id}&search=WDZ")
        self.assertEqual(response.status_code, 200)
        hrefs = self._category_chip_hrefs(response.text)
        self.assertEqual(hrefs, [f"{self.zone_page}?search=WDZ"])
        # Same address on the sidebar's own "Clear" button.
        clear = re.search(
            r'<a[^>]*class="wd-filter-link btn[^"]*"[^>]*href="([^"]*)"', response.text
        )
        self.assertIsNotNone(clear, "sidebar Clear button not rendered")
        self.assertEqual(
            _unlang(unescape(clear.group(1))), f"{self.zone_page}?search=WDZ"
        )

    def test_category_clear_chip_on_global_page(self):
        response = self.url_open(f"/comercio?category={self.leaf.id}&search=WDZ")
        hrefs = self._category_chip_hrefs(response.text)
        self.assertEqual(hrefs, ["/comercio?search=WDZ"])
        # From the category PATH route the chip must leave the category path
        # too, or it would clear nothing.
        response = self.url_open(f"/comercio/categoria/{self.leaf.id}?search=WDZ")
        hrefs = self._category_chip_hrefs(response.text)
        self.assertEqual(hrefs, ["/comercio?search=WDZ"])

    def test_category_form_exposes_selected_path(self):
        response = self.url_open(f"/comercio?category={self.leaf.id}")
        selected = self._attr(response.text, "wd_category_form", "data-selected")
        self.assertEqual(selected, f"[{self.root_category.id}, {self.leaf.id}, null]")
        response = self.url_open("/comercio")
        selected = self._attr(response.text, "wd_category_form", "data-selected")
        self.assertEqual(selected, "[null, null, null]")

    # ------------------------------------------------------------------
    # AJAX endpoint honours an explicit zone
    # ------------------------------------------------------------------
    def test_ajax_search_zone_param_narrows(self):
        response = self.url_open(
            f"/comercio/ajax/search?zone={ZONE_A}&category={self.leaf.id}&search=WDZ"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDZ Alpha Guanarteme", response.text)
        self.assertNotIn("WDZ Beta Tamaraceite", response.text)
        # The sidebar rendered by the same response is built on the zone
        # path, and does not leak `zone=` into the filter links.
        self.assertEqual(
            self._category_chip_hrefs(response.text), [f"{self.zone_page}?search=WDZ"]
        )
        self.assertNotIn("zone=", response.text)

    def test_ajax_search_legacy_zone_alias_is_normalised(self):
        response = self.url_open(
            "/comercio/ajax/search?zone=lomo_los_frailes&search=WDZ"
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WDZ Alpha Guanarteme", response.text)
        self.assertNotIn("WDZ Beta Tamaraceite", response.text)

    def test_ajax_search_invalid_zone_falls_back_to_website(self):
        # The test website is the global portal: both fixtures show.
        response = self.url_open("/comercio/ajax/search?zone=nowhere&search=WDZ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDZ Alpha Guanarteme", response.text)
        self.assertIn("WDZ Beta Tamaraceite", response.text)
        self.assertEqual(
            self._attr(response.text, "wd_category_form", "action"), "/comercio"
        )

    # ------------------------------------------------------------------
    # A stray ?zone= in the query string is never a 500
    # ------------------------------------------------------------------
    def test_stray_zone_query_param_is_harmless(self):
        """``zone`` used to reach ``_prepare_directory_values`` twice (as the
        computed keyword AND inside ``**kw``): a TypeError, i.e. a 500."""
        for path in (
            f"/comercio?zone={ZONE_A}&search=WDZ",
            f"/comercio/categoria/{self.leaf.id}?zone={ZONE_A}",
            f"{self.zone_page}?zone={ZONE_B}&search=WDZ",
            "/comercio?zone=nowhere",
        ):
            response = self.url_open(path)
            self.assertEqual(response.status_code, 200, path)
            for value in self._zone_option_values(response.text):
                self.assertNotIn("zone=", value, path)
        # The query string does not change the page's zone: the global page
        # still lists both fixtures, the zone path keeps its own zone.
        response = self.url_open(f"/comercio?zone={ZONE_A}&search=WDZ")
        self.assertIn("WDZ Beta Tamaraceite", response.text)
        response = self.url_open(f"{self.zone_page}?zone={ZONE_B}&search=WDZ")
        self.assertIn("WDZ Alpha Guanarteme", response.text)
        self.assertNotIn("WDZ Beta Tamaraceite", response.text)

    # ------------------------------------------------------------------
    # A website pinned to a zone is never steerable through ?zone=
    # ------------------------------------------------------------------
    def _pinned(self, zone):
        """The test website resolved as a marketplace pinned to ``zone``.

        Same outcome as ``test_zone_resolution.py``'s ``marketplace_zone``
        fixtures, at the level the AJAX route reads it; the HTTP server
        thread shares this process, so patching the class is enough.
        """
        return patch.object(
            WebsiteDirectory, "_get_zone_from_website", return_value=zone
        )

    def test_ajax_pinned_website_ignores_other_zone(self):
        with self._pinned(ZONE_B):
            response = self.url_open(f"/comercio/ajax/search?zone={ZONE_A}&search=WDZ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDZ Beta Tamaraceite", response.text)
        self.assertNotIn("WDZ Alpha Guanarteme", response.text)
        # Filter links stay on the host's own directory, not a zone path
        # (the zone select's own option values are the one legitimate place
        # for /comercio/zona/... addresses).
        self.assertEqual(
            self._attr(response.text, "wd_category_form", "action"), "/comercio"
        )

    def test_ajax_pinned_website_is_not_widened_by_canarias(self):
        with self._pinned(ZONE_B):
            response = self.url_open("/comercio/ajax/search?zone=canarias&search=WDZ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDZ Beta Tamaraceite", response.text)
        self.assertNotIn("WDZ Alpha Guanarteme", response.text)

    def test_ajax_global_website_honours_zone(self):
        with self._pinned("canarias"):
            response = self.url_open(f"/comercio/ajax/search?zone={ZONE_A}&search=WDZ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDZ Alpha Guanarteme", response.text)
        self.assertNotIn("WDZ Beta Tamaraceite", response.text)

    def test_pinned_website_page_ignores_zone_query(self):
        with self._pinned(ZONE_B):
            response = self.url_open(f"/comercio?zone={ZONE_A}&search=WDZ")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDZ Beta Tamaraceite", response.text)
        self.assertNotIn("WDZ Alpha Guanarteme", response.text)


class ChipBrowserMixin(ZoneFixtures):
    """The chip "x" really clears the category through the AJAX path.

    One ``HttpCase`` class per scenario on purpose: a second ``browser_js``
    in the same class trips the harness teardown (``Page.stopScreencast``
    on an already closed websocket) after the test itself passed.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls._setup_zone_fixtures()

    def _click_chip_and_wait(self, expected_path):
        """Load the module script, click the category chip, wait for the
        AJAX swap and check what is left on the page.

        The script is injected by hand: on the public website Odoo loads
        ``web.assets_frontend_lazy`` (where this module's script lives) on
        ``window.load``, and in the headless run that event never comes, so
        without this the click would be a plain navigation and prove
        nothing about the script.
        """
        return """
            (function () {
                function fail(message) { console.error(message); }
                function run() {
                    var chip = document.querySelector('a.wd-filter-link.wd-filter-chip-x');
                    if (!chip) { return fail('no category chip rendered'); }
                    var requests = [];
                    var nativeFetch = window.fetch;
                    window.fetch = function (url) {
                        requests.push(String(url));
                        return nativeFetch.apply(this, arguments);
                    };
                    chip.click();
                    var tries = 0;
                    var timer = setInterval(function () {
                        tries += 1;
                        var stillThere = document.querySelector('a.wd-filter-link.wd-filter-chip-x');
                        var badge = document.getElementById('wd_category_badge');
                        if (!stillThere && !badge) {
                            clearInterval(timer);
                            if (!requests.length) {
                                return fail('the chip navigated instead of fetching');
                            }
                            if (requests[0].indexOf('/comercio/ajax/search') === -1) {
                                return fail('unexpected request ' + requests[0]);
                            }
                            if (!/[?&]zone=%(zone)s(&|$)/.test(requests[0]) !== %(global)s) {
                                return fail('zone parameter wrong in ' + requests[0]);
                            }
                            // The website layer may prefix the path with /<lang>.
                            if (!window.location.pathname.endsWith('%(path)s')) {
                                return fail('pathname changed to ' + window.location.pathname);
                            }
                            if (window.location.search !== '?search=WDZ') {
                                return fail('query is ' + window.location.search);
                            }
                            if (!document.body.textContent.includes('WDZ Alpha Guanarteme')) {
                                return fail('zone entry missing after clearing the category');
                            }
                            if (document.body.textContent.includes('WDZ Beta Tamaraceite') !== %(global)s) {
                                return fail('other-zone entry visibility wrong after clearing');
                            }
                            var l2 = document.getElementById('wd_cat_l2_wrap');
                            if (l2 && !l2.classList.contains('d-none')) {
                                return fail('subcategory cascade still shows the cleared selection');
                            }
                            console.log('test successful');
                        } else if (tries > 100) {
                            clearInterval(timer);
                            fail('category chip never went away');
                        }
                    }, 100);
                }
                var script = document.createElement('script');
                script.src = '/website_directory/static/src/js/website_directory.js';
                script.onload = run;
                script.onerror = function () { fail('module script failed to load'); };
                document.head.appendChild(script);
            })();
        """ % {
            "path": expected_path,
            "zone": ZONE_A,
            "global": "true" if expected_path == "/comercio" else "false",
        }


@tagged("post_install", "-at_install")
class TestChipBrowserGlobal(ChipBrowserMixin, HttpCase):
    def test_browser_category_chip_clears_on_global_page(self):
        self.browser_js(
            f"/comercio?category={self.leaf.id}&search=WDZ",
            self._click_chip_and_wait("/comercio"),
            ready=READY,
        )


@tagged("post_install", "-at_install")
class TestChipBrowserZone(ChipBrowserMixin, HttpCase):
    def test_browser_category_chip_clears_on_zone_page(self):
        self.browser_js(
            f"{self.zone_page}?category={self.leaf.id}&search=WDZ",
            self._click_chip_and_wait(self.zone_page),
            ready=READY,
        )
