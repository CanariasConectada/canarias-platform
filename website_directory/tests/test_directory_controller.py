# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestDirectoryController(HttpCase):
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

    def test_directory_page_ok(self):
        response = self.url_open("/directorio")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertIn("WDC Beta Cafe", response.text)

    def test_hidden_company_not_listed(self):
        response = self.url_open("/directorio")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WDC Hidden Shop", response.text)

    def test_unpublished_entry_not_listed(self):
        response = self.url_open("/directorio")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WDC Unpublished Bar", response.text)

    def test_search_filter(self):
        response = self.url_open("/directorio?search=Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Beta Cafe", response.text)

    def test_category_filter_includes_descendants(self):
        # Filtering by the root (view) category must include the companies
        # of all descendant categories (child_of semantics).
        response = self.url_open(f"/directorio/categoria/{self.root_category.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertIn("WDC Beta Cafe", response.text)

    def test_category_filter_leaf_only(self):
        response = self.url_open(f"/directorio/categoria/{self.leaf_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        self.assertNotIn("WDC Beta Cafe", response.text)

    def test_category_filter_query_param(self):
        response = self.url_open(f"/directorio?category={self.leaf_b.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Beta Cafe", response.text)
        self.assertNotIn("WDC Alpha Bakery", response.text)

    def test_unknown_category_not_found(self):
        response = self.url_open("/directorio/categoria/99999999")
        self.assertEqual(response.status_code, 404)

    def test_pagination_out_of_range(self):
        response = self.url_open("/directorio/page/999")
        self.assertEqual(response.status_code, 200)

    def test_invalid_page_and_ppg_fall_back(self):
        response = self.url_open("/directorio?page=abc&ppg=7")
        self.assertEqual(response.status_code, 200)
        response = self.url_open("/directorio?ppg=abc")
        self.assertEqual(response.status_code, 200)

    def test_zone_route_ok(self):
        response = self.url_open("/directorio/zona/guanarteme")
        self.assertEqual(response.status_code, 200)

    def test_ajax_search_partial(self):
        response = self.url_open("/directorio/ajax/search?search=Alpha")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WDC Alpha Bakery", response.text)
        # Partial rendering: no full page layout.
        self.assertNotIn("<html", response.text[:200])

    def test_image_route_mimetype(self):
        response = self.url_open(f"/directorio/img/{self.entry_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers.get("Content-Type", "").startswith("image/"))

    def test_image_route_unpublished_not_found(self):
        response = self.url_open(f"/directorio/img/{self.entry_unpublished.id}")
        self.assertEqual(response.status_code, 404)

    def test_shuffle_cookie_set(self):
        response = self.url_open("/directorio")
        self.assertEqual(response.status_code, 200)
        cookies = response.headers.get("Set-Cookie", "")
        self.assertIn("directory_seed", cookies)
