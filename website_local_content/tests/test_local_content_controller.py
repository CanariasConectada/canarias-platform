# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged

from .common import create_taxonomy, make_test_image


@tagged("post_install", "-at_install")
class TestLocalContentController(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.type_a, cls.category_a, cls.subcategory_a = create_taxonomy(cls.env, "C")
        Item = cls.env["website.local.content.item"]
        cls.item_public = Item.create(
            {
                "name": "WLC Public Cinema",
                "type_id": cls.type_a.id,
                "category_id": cls.category_a.id,
                "subcategory_id": cls.subcategory_a.id,
                "description": "A public test item",
                "photo_year": 1958,
                "state": "approved",
                "is_published": True,
                "image_1920": make_test_image(),
            }
        )
        cls.item_pending = Item.create(
            {
                "name": "WLC Hidden Draft Item",
                "type_id": cls.type_a.id,
                "category_id": cls.category_a.id,
                "state": "pending",
            }
        )
        cls.index_url = "/explora/test-type-c"
        # A website that never matches the test HTTP requests: items or
        # types scoped to it must disappear from the default website.
        cls.other_website = cls.env["website"].create(
            {"name": "WLC Other Site", "domain": "https://wlc-other.example.com"}
        )
        cls.item_other_site = Item.create(
            {
                "name": "WLC Other Site Item",
                "type_id": cls.type_a.id,
                "category_id": cls.category_a.id,
                "state": "approved",
                "is_published": True,
                "website_ids": [(6, 0, cls.other_website.ids)],
                "image_1920": make_test_image(),
            }
        )

    def setUp(self):
        super().setUp()
        # Pinned to the website's default language: since the seven-language
        # rollout the anonymous negotiation can land on en_US, turning every
        # unprefixed request into a 303 hop this class does not expect.
        website = self.env["website"].search([], limit=1)
        self.opener.cookies["frontend_lang"] = website.default_lang_id.code

    def test_index_ok(self):
        response = self.url_open(self.index_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("WLC Public Cinema", response.text)
        self.assertIn("Test Type C", response.text)

    def test_index_hides_unapproved(self):
        response = self.url_open(self.index_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("WLC Hidden Draft Item", response.text)

    def test_index_search_filter(self):
        response = self.url_open(f"{self.index_url}?search=Cinema")
        self.assertIn("WLC Public Cinema", response.text)
        response = self.url_open(f"{self.index_url}?search=zzz-no-match")
        self.assertNotIn("WLC Public Cinema", response.text)

    def test_category_page_ok(self):
        response = self.url_open(f"{self.index_url}/categoria/{self.category_a.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WLC Public Cinema", response.text)

    def test_decade_filter(self):
        response = self.url_open(f"{self.index_url}?decade=1950")
        self.assertIn("WLC Public Cinema", response.text)
        response = self.url_open(f"{self.index_url}?decade=1990")
        self.assertNotIn("WLC Public Cinema", response.text)

    def test_detail_ok(self):
        response = self.url_open(f"{self.index_url}/{self.item_public.slug}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("WLC Public Cinema", response.text)
        self.assertIn("1958", response.text)

    def test_detail_unapproved_404(self):
        response = self.url_open(f"{self.index_url}/{self.item_pending.slug}")
        self.assertEqual(response.status_code, 404)

    def test_unknown_type_404(self):
        response = self.url_open("/explora/no-such-type")
        self.assertEqual(response.status_code, 404)

    # ------------------------------------------------------------------
    # Per-website scoping (parity with the legacy per-zone modules)
    # ------------------------------------------------------------------
    def test_index_hides_other_website_items(self):
        response = self.url_open(self.index_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("WLC Public Cinema", response.text)
        self.assertNotIn("WLC Other Site Item", response.text)

    def test_detail_other_website_404(self):
        response = self.url_open(f"{self.index_url}/{self.item_other_site.slug}")
        self.assertEqual(response.status_code, 404)

    def test_image_other_website_404(self):
        response = self.url_open(f"{self.index_url}/img/{self.item_other_site.id}")
        self.assertEqual(response.status_code, 404)

    def test_type_scoped_to_other_website_404(self):
        self.type_a.website_ids = [(6, 0, self.other_website.ids)]
        self.addCleanup(setattr, self.type_a, "website_ids", [(5, 0, 0)])
        response = self.url_open(self.index_url)
        self.assertEqual(response.status_code, 404)

    def test_page_titles(self):
        response = self.url_open(self.index_url)
        self.assertIn("<title>Test Type C", response.text)
        response = self.url_open(f"{self.index_url}/{self.item_public.slug}")
        self.assertIn("<title>WLC Public Cinema - Test Type C", response.text)

    def test_image_ok(self):
        response = self.url_open(f"{self.index_url}/img/{self.item_public.id}")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.headers["Content-Type"].startswith("image/"))

    def test_image_unapproved_404(self):
        response = self.url_open(f"{self.index_url}/img/{self.item_pending.id}")
        self.assertEqual(response.status_code, 404)

    def test_like_flow(self):
        like_url = f"{self.index_url}/like/{self.item_public.id}"
        csrf_token = self._get_csrf_token()
        response = self.url_open(like_url, data={"csrf_token": csrf_token})
        self.assertEqual(response.status_code, 200)  # after redirect
        self.env.invalidate_all()
        self.assertEqual(self.item_public.like_count, 1)
        # Same session likes again (reusing the session token: the liked
        # button no longer renders a form): no duplicate is created.
        self.url_open(like_url, data={"csrf_token": csrf_token})
        self.env.invalidate_all()
        self.assertEqual(self.item_public.like_count, 1)

    def test_like_open_redirect_blocked(self):
        """A crafted `redirect` (incl. the `/\\evil.com` backslash bypass)
        must never send the visitor off-site; it falls back to the item URL.
        """
        like_url = f"{self.index_url}/like/{self.item_public.id}"
        csrf_token = self._get_csrf_token()
        for hostile in ("http://evil.com", "//evil.com", "/\\evil.com"):
            response = self.url_open(
                like_url,
                data={"csrf_token": csrf_token, "redirect": hostile},
                allow_redirects=False,
            )
            self.assertIn(response.status_code, (302, 303))
            location = response.headers["Location"]
            self.assertNotIn("evil.com", location)
            self.assertTrue(location.endswith(self.item_public.website_url))

    def test_detail_external_website_is_safe(self):
        """A scheme-less external link renders as an https href with
        rel="noopener nofollow" (getter callable from QWeb, no XSS).
        """
        item = self.env["website.local.content.item"].create(
            {
                "name": "WLC Linked Place",
                "type_id": self.type_a.id,
                "category_id": self.category_a.id,
                "state": "approved",
                "is_published": True,
                "external_website": "www.example.com",
            }
        )
        response = self.url_open(f"{self.index_url}/{item.slug}")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="https://www.example.com"', response.text)
        self.assertIn('rel="noopener nofollow"', response.text)

    def _get_csrf_token(self):
        """Fetch a page first so the session gets a CSRF-capable cookie."""
        response = self.url_open(self.index_url)
        marker = 'name="csrf_token" value="'
        start = response.text.index(marker) + len(marker)
        return response.text[start : response.text.index('"', start)]

    def test_seeded_types_available(self):
        for slug in ("memoria-viva", "lugares-de-interes"):
            response = self.url_open(f"/explora/{slug}")
            self.assertEqual(
                response.status_code, 200, f"/explora/{slug} should render"
            )

    def test_legacy_redirects(self):
        for legacy, target in (
            ("/memoria-viva", "/explora/memoria-viva"),
            ("/lugares-de-interes", "/explora/lugares-de-interes"),
            ("/memoria-viva/some-slug", "/explora/memoria-viva/some-slug"),
        ):
            response = self.url_open(legacy, allow_redirects=False)
            self.assertEqual(response.status_code, 301)
            self.assertTrue(response.headers["Location"].endswith(target))

    # ------------------------------------------------------------------
    # Legacy design port: page size, sorts, hero, sponsor band
    # ------------------------------------------------------------------
    def _create_bulk_items(self, count):
        Item = self.env["website.local.content.item"]
        return Item.create(
            [
                {
                    "name": f"WLC Bulk Item {index:02d}",
                    "type_id": self.type_a.id,
                    "category_id": self.category_a.id,
                    "state": "approved",
                    "is_published": True,
                }
                for index in range(1, count + 1)
            ]
        )

    def test_limit_whitelist(self):
        """?limit= only honours 12/24/48; anything else falls back to 12."""
        self._create_bulk_items(13)
        # 14 visible items, default sort is id-descending: the oldest bulk
        # item overflows to page 2 with the default page size of 12.
        response = self.url_open(self.index_url)
        self.assertNotIn("WLC Bulk Item 01", response.text)
        self.assertIn('class="pagination', response.text)
        # An allowed larger page size shows everything on page 1.
        response = self.url_open(f"{self.index_url}?limit=24")
        self.assertIn("WLC Bulk Item 01", response.text)
        self.assertIn("WLC Public Cinema", response.text)
        # A value outside the whitelist behaves exactly like the default.
        for bad_limit in ("7", "0", "-5", "1000", "abc"):
            response = self.url_open(f"{self.index_url}?limit={bad_limit}")
            self.assertEqual(response.status_code, 200)
            self.assertNotIn("WLC Bulk Item 01", response.text)

    def test_pager_preserves_query_string(self):
        self._create_bulk_items(13)
        response = self.url_open(f"{self.index_url}?search=WLC")
        self.assertIn("/page/2?search=WLC#entries_grid", response.text)

    def test_sort_options_ok(self):
        for sort in ("rating", "likes", "newest", "oldest"):
            response = self.url_open(f"{self.index_url}?sort={sort}")
            self.assertEqual(response.status_code, 200)
            self.assertIn("WLC Public Cinema", response.text)

    def test_image_size_variants(self):
        for query in ("", "?size=512", "?size=1024", "?size=evil"):
            response = self.url_open(
                f"{self.index_url}/img/{self.item_public.id}{query}"
            )
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["Content-Type"].startswith("image/"))

    def test_hero_image_rendered(self):
        hero_url = f"{self.index_url}/n/hero_image"
        # Without a hero image: gradient fallback, streaming route 404s.
        response = self.url_open(self.index_url)
        self.assertNotIn(hero_url, response.text)
        self.assertEqual(self.url_open(hero_url).status_code, 404)
        self.type_a.hero_image = make_test_image()
        self.type_a.hero_subtitle = "WLC Hero Subtitle"
        response = self.url_open(self.index_url)
        self.assertIn(hero_url, response.text)
        self.assertIn("WLC Hero Subtitle", response.text)
        image_response = self.url_open(hero_url)
        self.assertEqual(image_response.status_code, 200)
        self.assertTrue(
            image_response.headers["Content-Type"].startswith("image/")
        )

    def test_type_image_field_whitelist(self):
        response = self.url_open(f"{self.index_url}/n/create_uid")
        self.assertEqual(response.status_code, 404)

    def test_sponsor_band_gated_on_type(self):
        sponsor_url = f"{self.index_url}/n/sponsor_logo"
        response = self.url_open(self.index_url)
        self.assertNotIn(sponsor_url, response.text)
        self.type_a.sponsor_logo = make_test_image()
        self.type_a.sponsor_name = "WLC Sponsor"
        for page in (
            self.index_url,
            f"{self.index_url}/{self.item_public.slug}",
        ):
            response = self.url_open(page)
            self.assertIn(sponsor_url, response.text)
            self.assertIn('alt="WLC Sponsor"', response.text)

    def test_seeded_sponsor_only_on_living_memory(self):
        """The Gobierno de Canarias band is seeded on Living Memory only."""
        response = self.url_open("/explora/memoria-viva")
        self.assertIn("/explora/memoria-viva/n/sponsor_logo", response.text)
        self.assertIn("Gobierno de Canarias", response.text)
        response = self.url_open("/explora/lugares-de-interes")
        self.assertNotIn("n/sponsor_logo", response.text)

    def test_seeded_hero_images(self):
        for slug in ("memoria-viva", "lugares-de-interes"):
            response = self.url_open(f"/explora/{slug}")
            self.assertIn(f"/explora/{slug}/n/hero_image", response.text)
