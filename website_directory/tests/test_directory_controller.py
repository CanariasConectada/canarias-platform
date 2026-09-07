# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestDirectoryController(HttpCase):
    def setUp(self):
        super().setUp()
        # Pinned to the website's default language: since the seven-language
        # rollout the anonymous negotiation can land on en_US and every
        # unprefixed request becomes a 303 language hop first.
        website = self.env["website"].search([], limit=1)
        self.opener.cookies["frontend_lang"] = website.default_lang_id.code

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env["res.company.category"]
        cls.root_category = Category.create({"name": "WDC Root", "type": "view"})
        cls.leaf_a = Category.create(
            {"name": "WDC Leaf A", "type": "normal", "parent_id": cls.root_category.id}
        )
        cls.leaf_b = Category.create(
            {"name": "WDC Leaf B", "type": "normal", "parent_id": cls.root_category.id}
        )
        Company = cls.env["res.company"]
        cls.company_a = Company.create(
            {"name": "WDC Alpha Bakery", "category_id": cls.leaf_a.id}
        )
        cls.company_b = Company.create(
            {"name": "WDC Beta Cafe", "category_id": cls.leaf_b.id}
        )
        cls.company_hidden = Company.create(
            {"name": "WDC Hidden Shop", "show_in_directory": False}
        )
        cls.company_unpublished = Company.create({"name": "WDC Unpublished Bar"})
        # Directory sync is asynchronous (flagged on create, drained by cron):
        # flush the new companies so their entries exist for the assertions.
        new_companies = (
            cls.company_a | cls.company_b | cls.company_hidden | cls.company_unpublished
        )
        new_companies._sync_to_directory_entry()
        new_companies.directory_sync_pending = False
        Entry = cls.env["website.directory.entry"].sudo()
        cls.entry_a = Entry.search([("company_id", "=", cls.company_a.id)])
        cls.entry_unpublished = Entry.search(
            [("company_id", "=", cls.company_unpublished.id)]
        )
        cls.entry_unpublished.is_published = False
        # The hidden company's entry exists but is archived (active mirrors
        # show_in_directory), so active_test must be off to fetch it.
        cls.entry_hidden = Entry.with_context(active_test=False).search(
            [("company_id", "=", cls.company_hidden.id)]
        )

    # These three narrow to the fixtures with ?search=WDC instead of reading
    # the bare first page. On an empty test database the fixtures happen to be
    # the whole directory; on a copy of production they are four rows among
    # hundreds and land on page 9. That made the positive test fail for the
    # wrong reason, and — worse — made the two negative tests below pass
    # vacuously: "hidden shop not on this page" is true of every company that
    # simply did not fit.
    def test_directory_page_ok(self):
        response = self.url_open("/comercio?search=WDC")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertIn("WDC Beta Cafe", response.text)

    def test_sidebar_levels_zone_then_category_then_extras(self):
        """The filters read top-down as levels: where (zone), then what
        (category), then the bridge modules' refinements underneath."""
        response = self.url_open("/comercio")
        self.assertEqual(response.status_code, 200)
        zone = response.text.find('id="wd_zone_card"')
        category = response.text.find('id="wd_category_card"')
        extras = response.text.find('id="o_wd_sidebar_extra"')
        self.assertGreater(zone, -1)
        self.assertGreater(category, zone, "category filter must follow zone")
        self.assertGreater(extras, category, "bridge filters close the column")

    def test_category_filter_offers_every_active_root(self):
        """No pruning: every active root category is an option; an archived
        one is not offered."""
        archived = self.env["res.company.category"].create(
            {"name": "WDC Archived Root", "type": "view", "active": False}
        )
        response = self.url_open("/comercio")
        self.assertEqual(response.status_code, 200)
        roots = (
            self.env["res.company.category"].sudo().search([("parent_id", "=", False)])
        )
        self.assertNotIn(archived, roots)
        self.assertIn("WDC Root", response.text)
        self.assertNotIn("WDC Archived Root", response.text)

    def test_browser_title_does_not_repeat_the_site_name(self):
        """The tab says where you are; the site name is appended by the layout.

        ``website.layout`` builds the title as "<additional_title> | <site>".
        While the tab and the H1 shared one term, the portal's tab read
        "Directorio Canarias Conectada | Canarias Conectada" and a merchant
        microsite's read the platform's brand next to the shop's own.
        """
        response = self.url_open("/comercio")
        self.assertEqual(response.status_code, 200)
        title = re.search(r"<title>(.*?)</title>", response.text, re.S).group(1)
        head, _sep, site = title.rpartition("|")
        self.assertTrue(_sep, "the layout appends the site name after a pipe")
        self.assertNotIn(site.strip(), head, title)

    def test_hidden_company_not_listed(self):
        response = self.url_open("/comercio?search=WDC")
        self.assertEqual(response.status_code, 200)
        # Positive control first: without it, an empty result page would
        # satisfy the assertion below and prove nothing about the filtering.
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Hidden Shop", response.text)

    def test_unpublished_entry_not_listed(self):
        response = self.url_open("/comercio?search=WDC")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Unpublished Bar", response.text)

    def test_search_filter(self):
        response = self.url_open("/comercio?search=Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Beta Cafe", response.text)

    def test_search_is_word_order_independent(self):
        """Words typed in any order must find the same shop.

        Matching the whole query as one ``ilike`` made order decide the
        result: on production "muebles siony" found the shop and "siony
        muebles" found nothing, because the substring never occurs that way.
        """
        for query in ("Alpha+Bakery", "Bakery+Alpha"):
            response = self.url_open(f"/comercio?search={query}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("WDC Alpha Bakery", response.text, f"query: {query}")

    def test_search_requires_every_word(self):
        """Words are ANDed, so an extra word that matches nothing excludes the
        entry instead of widening the result set."""
        response = self.url_open("/comercio?search=Alpha+Cafe")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Beta Cafe", response.text)

    def test_category_filter_includes_descendants(self):
        # Filtering by the root (view) category must include the companies
        # of all descendant categories (child_of semantics).
        response = self.url_open(f"/comercio/categoria/{self.root_category.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertIn("WDC Beta Cafe", response.text)

    def test_category_filter_leaf_only(self):
        response = self.url_open(f"/comercio/categoria/{self.leaf_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Beta Cafe", response.text)

    def test_category_filter_query_param(self):
        response = self.url_open(f"/comercio?category={self.leaf_b.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Beta Cafe", response.text)
        self.assertNotIn("WDC Alpha Bakery", response.text)

    def test_unknown_category_not_found(self):
        response = self.url_open("/comercio/categoria/99999999")
        self.assertEqual(response.status_code, 404)

    def test_pagination_out_of_range(self):
        response = self.url_open("/comercio/page/999")
        self.assertEqual(response.status_code, 200)

    def test_invalid_page_and_ppg_fall_back(self):
        response = self.url_open("/comercio?page=abc&ppg=7")
        self.assertEqual(response.status_code, 200)
        response = self.url_open("/comercio?ppg=abc")
        self.assertEqual(response.status_code, 200)

    def test_zone_route_ok(self):
        response = self.url_open("/comercio/zona/guanarteme")
        self.assertEqual(response.status_code, 200)

    def test_clear_filters_trash_visibility(self):
        # With an active filter the red trash (clear-all) must be rendered...
        response = self.url_open(f"/comercio/categoria/{self.leaf_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("wd-clear-filters", response.text)
        response = self.url_open("/comercio?search=Alpha")
        self.assertIn("wd-clear-filters", response.text)
        # ...and on the bare directory there is nothing to clear.
        response = self.url_open("/comercio")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("wd-clear-filters", response.text)

    def _selected_chips(self, html):
        """Every ``directory_filter_chip`` anchor in the page, whole.

        Whole, not just the opening tag, because what has to be asserted is
        that the cross lives INSIDE the chip. No chip nests an anchor, so a
        non-greedy match up to </a> cannot overshoot.
        """
        return re.findall(
            r'<a[^>]*class="wd-filter-selected[^"]*"[^>]*>.*?</a>', html, re.DOTALL
        )

    def test_every_selected_filter_is_the_shared_remove_chip(self):
        """One deselect affordance for the whole sidebar.

        Reported 2026-09-05: each section had grown its own (a small "x",
        a "Clear" button, a trash icon). The zone and the category are the
        base module's own sections; the bridge modules cover theirs.
        """
        response = self.url_open(f"/comercio/categoria/{self.leaf_a.id}")
        self.assertEqual(response.status_code, 200)
        chips = self._selected_chips(response.text)
        # The sidebar card and the top summary bar: the same chip twice,
        # each one named after the filter it removes.
        self.assertEqual(len(chips), 2, chips)
        for chip in chips:
            self.assertIn("wd-filter-link", chip)
            self.assertIn('title="WDC Leaf A"', chip)
            self.assertIn('class="wd-filter-remove"', chip)
            # The accessible name is content, not an aria-label: a static
            # text node is the only shape QWeb hands to the translator
            # readably. Asserted by class, because the words themselves
            # arrive in the website's own language.
            self.assertIn('class="visually-hidden"', chip)
        # The zone chip is the same control, minus the AJAX hook: removing
        # the zone is a real navigation.
        response = self.url_open("/comercio/zona/guanarteme")
        self.assertEqual(response.status_code, 200)
        chips = self._selected_chips(response.text)
        self.assertEqual(len(chips), 2, chips)
        for chip in chips:
            self.assertNotIn("wd-filter-link", chip)
            self.assertIn('class="wd-filter-remove"', chip)
        # Nothing selected, nothing to remove.
        response = self.url_open("/comercio")
        self.assertNotIn("wd-filter-selected", response.text)
        self.assertNotIn("wd-filter-remove", response.text)

    def test_the_clear_all_button_wears_the_same_cross(self):
        """One "remove" glyph per page: the clear-all dropped its trash for
        the cross the chips use, keeping its own accessible name because it
        clears every filter rather than the one it sits next to."""
        response = self.url_open(f"/comercio/categoria/{self.leaf_a.id}")
        clear_all = re.search(
            r'<a[^>]*class="[^"]*wd-clear-filters[^"]*"[^>]*>.*?</a>',
            response.text,
            re.DOTALL,
        )
        self.assertIsNotNone(clear_all, "clear-all button not rendered")
        self.assertIn("fa-times", clear_all.group(0))
        self.assertNotIn("fa-trash", clear_all.group(0))
        self.assertRegex(clear_all.group(0), r"aria-label=\"[^\"]+\"")

    def test_ajax_search_partial(self):
        response = self.url_open("/comercio/ajax/search?search=Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        # Partial rendering: no full page layout.
        self.assertNotIn("<html", response.text[:200])

    def test_image_route_mimetype(self):
        response = self.url_open(f"/comercio/img/{self.entry_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("Content-Type", "").startswith("image/"))

    def test_image_route_unpublished_not_found(self):
        response = self.url_open(f"/comercio/img/{self.entry_unpublished.id}")
        self.assertEqual(response.status_code, 404)

    def test_image_route_hidden_company_not_found(self):
        # IDOR guard: the entry of a company with show_in_directory=False
        # (hence an archived entry) must not leak its logo through the
        # enumerable public image route.
        self.assertFalse(self.entry_hidden.company_id.show_in_directory)
        response = self.url_open(f"/comercio/img/{self.entry_hidden.id}")
        self.assertEqual(response.status_code, 404)

    def test_image_route_visible_ok(self):
        # The counterpart of the IDOR guard: a fully visible entry serves
        # its image with a 200.
        response = self.url_open(f"/comercio/img/{self.entry_a.id}")
        self.assertEqual(response.status_code, 200)

    def test_shuffle_cookie_set(self):
        response = self.url_open("/comercio")
        self.assertEqual(response.status_code, 200)
        cookies = response.headers.get("Set-Cookie", "")
        self.assertIn("directory_seed", cookies)

    def test_legacy_directorio_redirects(self):
        # Old /directorio URLs must 301 to /comercio keeping path and query.
        response = self.url_open("/directorio", allow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["Location"].endswith("/comercio"))
        response = self.url_open(
            f"/directorio/categoria/{self.leaf_a.id}", allow_redirects=False
        )
        self.assertEqual(response.status_code, 301)
        self.assertTrue(
            response.headers["Location"].endswith(
                f"/comercio/categoria/{self.leaf_a.id}"
            )
        )
        response = self.url_open("/directorio?search=Alpha", allow_redirects=False)
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response.headers["Location"].endswith("/comercio?search=Alpha"))
        # Followed, the legacy URL lands on the working page.
        response = self.url_open("/directorio?search=Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
