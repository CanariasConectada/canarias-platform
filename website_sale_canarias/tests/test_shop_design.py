# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import json

from odoo.tests import HttpCase, tagged

# 1x1 red PNG. Small enough to inline, real enough for image_process.
TINY_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
        "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
)


@tagged("post_install", "-at_install")
class TestShopDesign(HttpCase):
    """The aggregated shop's look and its AJAX endpoint, over real HTTP.

    Run with a dbfilter that matches the test database: inside a deployment
    container the config pins the HTTP layer to the production database and
    every assertion silently reads the wrong site.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.category = cls.env["product.public.category"].create(
            {"name": "WSC Alimentación"}
        )
        # auto_microsite_generator (co-installed in the full CI run) would
        # give this newborn merchant a second, auto-provisioned website whose
        # seeded domain then wins the company.website_id race against the
        # explicit fixture site below. The suite builds its own site with the
        # exact domain it asserts on, so create the company under the
        # documented opt-out and keep this fixture the only site maker.
        cls.merchant = (
            cls.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "WSC Panadería SL"})
        )
        cls.merchant_site = cls.env["website"].create(
            {
                "name": "WSC Panadería",
                "company_id": cls.merchant.id,
                "domain": "https://wsc-panaderia.example",
            }
        )
        cls.product = cls.env["product.template"].create(
            {
                "name": "WSC Pan de Millo",
                "sale_ok": True,
                "is_published": True,
                "list_price": 25.0,
                "company_ids": [(6, 0, [cls.merchant.id])],
                "public_categ_ids": [(6, 0, [cls.category.id])],
                # First in the shop order: a new product is born with the
                # highest website_sequence, and on a database whose demo
                # catalogue already fills page 1 the card under test would
                # otherwise land on page 2, out of the rendered page.
                "website_sequence": 1,
            }
        )
        # The portal is flagged AFTER the product exists so the marketplace
        # backfill links it — the same order the live platform went through.
        cls.portal = cls.env["website"].search([], order="id", limit=1)
        cls.portal.is_marketplace = True

    # ------------------------------------------------------------------
    # The page
    # ------------------------------------------------------------------

    def test_portal_shop_wears_the_canarias_design(self):
        """Hero on, stock toolbar off, sidebar select on — the three moves
        that turn Odoo's shop into the platform's shop."""
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tienda Canarias Conectada", response.text)
        self.assertIn("wsc_category_select", response.text)
        self.assertNotIn('id="o_wsale_products_header"', response.text)

    def test_portal_card_names_the_merchant(self):
        """An aggregated shop sells nothing itself: every card must say
        whose shop window it is."""
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wsc_pill_badge", response.text)
        self.assertIn("WSC Panadería SL", response.text)

    def test_sidebar_offers_the_shop_categories(self):
        self.assertIn(self.category, self.portal._wsc_shop_categories())
        response = self.url_open("/shop")
        self.assertIn("WSC Alimentación", response.text)

    # ------------------------------------------------------------------
    # The two-level category tree
    # ------------------------------------------------------------------

    def _add_child_category_product(self):
        """A product filed only under a child of the existing category."""
        child = self.env["product.public.category"].create(
            {"name": "WSC Panadería Artesana", "parent_id": self.category.id}
        )
        product = self.env["product.template"].create(
            {
                "name": "WSC Bollo de Anís",
                "sale_ok": True,
                "is_published": True,
                "list_price": 4.0,
                "company_ids": [(6, 0, [self.merchant.id])],
                "public_categ_ids": [(6, 0, [child.id])],
            }
        )
        return child, product

    def test_category_tree_hangs_children_under_their_parent(self):
        child, _product = self._add_child_category_product()
        tree = self.portal._wsc_shop_category_tree()
        node = [n for n in tree if self.category in n["categories"]]
        self.assertTrue(node, "the parent category must be a top level")
        self.assertIn(
            child,
            [c for entry in node[0]["children"] for c in entry["categories"]],
        )
        # Nothing pruned: the flat set and the tree carry the same categories.
        flat = self.portal._wsc_shop_categories()
        in_tree = set()
        for n in tree:
            in_tree.update(n["categories"].ids)
            for entry in n["children"]:
                in_tree.update(entry["categories"].ids)
        self.assertEqual(set(flat.ids), in_tree)

    def test_selected_category_path_places_the_selection(self):
        child, _product = self._add_child_category_product()
        self.assertEqual(
            self.portal._wsc_selected_category_path(self.category),
            (self.category.id, None),
        )
        self.assertEqual(
            self.portal._wsc_selected_category_path(child),
            (self.category.id, child.id),
        )
        self.assertEqual(self.portal._wsc_selected_category_path(None), (None, None))

    def test_ajax_parent_category_includes_the_childs_products(self):
        """Picking a main category promises everything under it: a product
        filed ONLY under a child must come back for the parent — this is the
        child_of contract, and an exact-match domain would fail it."""
        child, product = self._add_child_category_product()
        result = self._ajax("?category=%s" % self.category.id)
        self.assertIn(product.name, result["html"])
        by_child = self._ajax("?category=%s" % child.id)
        self.assertIn(product.name, by_child["html"])
        self.assertNotIn("WSC Pan de Millo", by_child["html"])

    def test_category_tree_bridges_an_unlisted_middle_level(self):
        """A leaf whose immediate parent sells nothing here still hangs under
        the listed grandparent — the tree walks the whole ancestor chain, not
        one step."""
        middle = self.env["product.public.category"].create(
            {"name": "WSC Nivel Fantasma", "parent_id": self.category.id}
        )
        leaf = self.env["product.public.category"].create(
            {"name": "WSC Hoja Profunda", "parent_id": middle.id}
        )
        self.env["product.template"].create(
            {
                "name": "WSC Producto Profundo",
                "sale_ok": True,
                "is_published": True,
                "list_price": 2.0,
                "company_ids": [(6, 0, [self.merchant.id])],
                "public_categ_ids": [(6, 0, [leaf.id])],
            }
        )
        tree = self.portal._wsc_shop_category_tree()
        node = [n for n in tree if self.category in n["categories"]]
        self.assertTrue(node)
        self.assertIn(
            leaf,
            [c for entry in node[0]["children"] for c in entry["categories"]],
        )
        top_ids = set()
        for n in tree:
            top_ids.update(n["categories"].ids)
        self.assertNotIn(
            middle.id,
            top_ids,
            "a category no product carries is not a filter option",
        )

    def test_sidebar_renders_the_subcategory_level(self):
        child, _product = self._add_child_category_product()
        response = self.url_open("/shop?category=%s" % self.category.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("wsc_subcategory_select", response.text)
        self.assertIn(child.name, response.text)

    # ------------------------------------------------------------------
    # Same-named categories merge into one option
    # ------------------------------------------------------------------

    def _add_same_named_categories(self):
        """Two same-named categories, each with one product filed under it —
        the duplication every real merchant onboarding produced (each shop
        creates its own 'Accesorios')."""
        twin_a = self.env["product.public.category"].create({"name": "WSC Accesorios"})
        # Different spacing and case on purpose: merging must survive the
        # ways two humans type the same label.
        twin_b = self.env["product.public.category"].create({"name": "wsc  ACCESORIOS"})
        products = self.env["product.template"].create(
            [
                {
                    "name": "WSC Correa Artesana",
                    "sale_ok": True,
                    "is_published": True,
                    "list_price": 9.0,
                    "company_ids": [(6, 0, [self.merchant.id])],
                    "public_categ_ids": [(6, 0, [twin_a.id])],
                    "website_sequence": 2,
                },
                {
                    "name": "WSC Funda de Timple",
                    "sale_ok": True,
                    "is_published": True,
                    "list_price": 19.0,
                    "company_ids": [(6, 0, [self.merchant.id])],
                    "public_categ_ids": [(6, 0, [twin_b.id])],
                    "website_sequence": 3,
                },
            ]
        )
        return twin_a, twin_b, products

    def test_same_named_categories_become_one_option(self):
        twin_a, twin_b, _products = self._add_same_named_categories()
        tree = self.portal._wsc_shop_category_tree()
        holding = [
            n for n in tree if twin_a in n["categories"] or twin_b in n["categories"]
        ]
        self.assertEqual(len(holding), 1, "one label, one option")
        self.assertIn(twin_a, holding[0]["categories"])
        self.assertIn(twin_b, holding[0]["categories"])
        # The representative id is the stable, lowest one; both members
        # resolve to the same merged group.
        expected = sorted([twin_a.id, twin_b.id])
        self.assertEqual(holding[0]["id"], expected[0])
        self.assertEqual(self.portal._wsc_merged_category_ids(twin_a.id), expected)
        self.assertEqual(self.portal._wsc_merged_category_ids(twin_b.id), expected)

    def test_ajax_merged_category_returns_both_merchants_products(self):
        twin_a, twin_b, products = self._add_same_named_categories()
        result = self._ajax("?category=%s" % min(twin_a.id, twin_b.id))
        for product in products:
            self.assertIn(product.name, result["html"])
        # Picking the NON-representative member widens all the same: the
        # promise belongs to the label, not to whichever record carries it.
        result = self._ajax("?category=%s" % max(twin_a.id, twin_b.id))
        for product in products:
            self.assertIn(product.name, result["html"])

    def test_full_page_reload_keeps_the_merged_group(self):
        """A reload renders through core's _get_shop_domain: without the
        widening override the grid would narrow to one record's subtree and
        disagree with the AJAX view of the same select."""
        twin_a, twin_b, products = self._add_same_named_categories()
        response = self.url_open("/shop?category=%s" % min(twin_a.id, twin_b.id))
        self.assertEqual(response.status_code, 200)
        for product in products:
            self.assertIn(product.name, response.text)

    # ------------------------------------------------------------------
    # The mobile toolbar and the offcanvas
    # ------------------------------------------------------------------

    def test_mobile_toolbar_reopens_the_filters_in_the_offcanvas(self):
        """Below lg the sidebar is display-none and the stock header — the
        only #o_wsale_offcanvas toggle — is gone: the slim toolbar's button
        and the offcanvas copy of the filter cards are the only way to
        filter or switch zones on a phone."""
        self.portal.domain = "https://wsc-portal.example"
        self.env["website"].create(
            {
                "name": "WSC Zona Móvil",
                "domain": "https://wsc-zona-movil.example",
                "is_marketplace": True,
            }
        )
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wsc_filters_btn", response.text)
        self.assertIn('data-bs-target="#o_wsale_offcanvas"', response.text)
        # The offcanvas holds its own suffixed instance of every filter card
        # (same fragment as the sidebar, so the two can never drift).
        self.assertIn("wsc_category_select_offcanvas", response.text)
        self.assertIn("wsc_zone_select_offcanvas", response.text)
        offcanvas = response.text.split('id="o_wsale_offcanvas"')[1]
        self.assertIn(
            "o_wsc_zone_card",
            offcanvas,
            "the zone switcher must be reachable from a phone",
        )

    # ------------------------------------------------------------------
    # The zone switcher
    # ------------------------------------------------------------------

    def test_zone_switcher_derives_from_marketplace_websites(self):
        """The switcher is configuration, not a hardcoded list: flag a second
        marketplace website and it appears, portal first."""
        self.portal.domain = "https://wsc-portal.example"
        zone_site = self.env["website"].create(
            {
                "name": "WSC Zona",
                "domain": "https://wsc-zona.example",
                "is_marketplace": True,
            }
        )
        selection = (
            self.env["website"]
            ._fields["marketplace_zone"]
            ._description_selection(self.env)
        )
        if selection:
            zone_site.marketplace_zone = selection[0][0]
        sites = self.portal._wsc_zone_sites()
        self.assertEqual(sites[0], self.portal, "the portal leads the list")
        self.assertIn(zone_site, sites)

        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("wsc_zone_select", response.text)
        self.assertIn("Todas las zonas", response.text)
        self.assertIn("https://wsc-zona.example/shop", response.text)

    def test_zone_switcher_needs_at_least_two_shops(self):
        """A switcher with one destination is dead UI — with only the portal
        flagged, the card stays off the page."""
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("wsc_zone_select", response.text)

    def test_microsite_gets_no_zone_switcher(self):
        self.portal.domain = "https://wsc-portal.example"
        self.env["website"].create(
            {
                "name": "WSC Zona",
                "domain": "https://wsc-zona.example",
                "is_marketplace": True,
            }
        )
        response = self.url_open("/shop", headers={"Host": "wsc-panaderia.example"})
        self.assertNotIn("wsc_zone_select", response.text)

    # ------------------------------------------------------------------
    # The AJAX endpoint
    # ------------------------------------------------------------------

    def _ajax(self, query=""):
        response = self.url_open("/shop/ajax/products" + query)
        self.assertEqual(response.status_code, 200)
        return json.loads(response.text)

    def test_ajax_lists_the_published_product(self):
        result = self._ajax()
        self.assertNotIn("error", result)
        self.assertGreaterEqual(result["count"], 1)
        self.assertIn("WSC Pan de Millo", result["html"])

    def test_ajax_filters_by_category_search_and_price(self):
        by_category = self._ajax("?category=%s" % self.category.id)
        self.assertIn("WSC Pan de Millo", by_category["html"])
        self.assertTrue(by_category["filters_active"])
        self.assertEqual(by_category["category_name"], "WSC Alimentación")

        no_match = self._ajax("?search=zzz-nada-zzz")
        self.assertEqual(no_match["count"], 0)
        self.assertIn("No se encontraron productos", no_match["html"])

        priced_out = self._ajax("?min_price=1000")
        self.assertNotIn("WSC Pan de Millo", priced_out["html"])

    def test_ajax_links_the_card_to_the_merchants_site(self):
        result = self._ajax()
        self.assertIn("https://wsc-panaderia.example/shop/", result["html"])

    def test_ajax_on_a_microsite_does_not_leak_other_merchants(self):
        """The endpoint searches as the public user, so the record rule — not
        the domain alone — bounds a microsite to its own catalogue. A second
        merchant's published product must never reach the first's shop AJAX.
        """
        other = self.env["res.company"].create({"name": "WSC Otra SL"})
        self.env["website"].create(
            {
                "name": "WSC Otra",
                "company_id": other.id,
                "domain": "https://wsc-otra.example",
            }
        )
        self.env["product.template"].create(
            {
                "name": "WSC Producto Ajeno",
                "sale_ok": True,
                "is_published": True,
                "list_price": 7.0,
                "company_ids": [(6, 0, [other.id])],
            }
        )
        response = self.url_open(
            "/shop/ajax/products", headers={"Host": "wsc-panaderia.example"}
        )
        body = json.loads(response.text)
        self.assertNotIn("WSC Producto Ajeno", body["html"])
        self.assertIn("WSC Pan de Millo", body["html"])

    def test_ajax_excludes_products_of_an_archived_merchant(self):
        """An archived merchant's catalogue must not come back through AJAX
        even on the aggregating portal — the record rule hides it once the
        marketplace links are gone, and the endpoint honours the rule."""
        # Under the AMG opt-out: an auto-provisioned microsite would make the
        # company unarchivable (core refuses to archive a company that still
        # owns a website), and this scenario needs a bare, archivable merchant.
        gone = (
            self.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": "WSC Retirada SL"})
        )
        self.env["product.template"].create(
            {
                "name": "WSC Producto Retirado",
                "sale_ok": True,
                "is_published": True,
                "list_price": 3.0,
                "company_ids": [(6, 0, [gone.id])],
            }
        )
        gone.active = False
        result = self._ajax()
        self.assertNotIn("WSC Producto Retirado", result["html"])

    # ------------------------------------------------------------------
    # A merchant microsite keeps its plain shop
    # ------------------------------------------------------------------

    def test_microsite_gets_no_hero_and_no_badge(self):
        response = self.url_open("/shop", headers={"Host": "wsc-panaderia.example"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("Tienda Canarias Conectada", response.text)
        self.assertNotIn("o_wsc_pill_badge", response.text)

    # ------------------------------------------------------------------
    # Category tiles + active filter chip
    # ------------------------------------------------------------------

    def test_tiles_only_top_level_curated_categories(self):
        """Curation lives on cover_image; only TOP-LEVEL categories tile — a
        subcategory with its own cover_image must never appear as a tile,
        even when its parent has none."""
        child, _product = self._add_child_category_product()
        child.cover_image = TINY_PNG
        tiles = self.portal._wsc_shop_category_tiles()
        tile_ids = {tile["category"].id for tile in tiles}
        self.assertNotIn(child.id, tile_ids)
        self.assertNotIn(
            self.category.id, tile_ids, "parent has no cover_image either"
        )

        self.category.cover_image = TINY_PNG
        tiles = self.portal._wsc_shop_category_tiles()
        tile_ids = {tile["category"].id for tile in tiles}
        self.assertIn(self.category.id, tile_ids)
        self.assertNotIn(child.id, tile_ids)

    def test_tile_image_falls_back_to_a_merged_members_cover(self):
        """The representative (lowest id) may have no photo; the tile must
        still show whichever merged member DOES, picked in ascending id
        order, while the URL keeps pointing at the representative."""
        twin_a, twin_b, _products = self._add_same_named_categories()
        representative = min(twin_a, twin_b, key=lambda category: category.id)
        other = twin_b if representative == twin_a else twin_a
        other.cover_image = TINY_PNG

        tiles = self.portal._wsc_shop_category_tiles()
        holding = [t for t in tiles if t["category"].id == representative.id]
        self.assertTrue(holding, "the representative id is what the URL carries")
        self.assertIn(
            "/web/image/product.public.category/%s/cover_image" % other.id,
            holding[0]["image_url"],
        )

    def test_tile_renders_exactly_one_image_when_several_members_have_covers(self):
        twin_a, twin_b, _products = self._add_same_named_categories()
        twin_a.cover_image = TINY_PNG
        twin_b.cover_image = TINY_PNG
        tiles = self.portal._wsc_shop_category_tiles()
        holding = [
            t for t in tiles if t["category"].id in (twin_a.id, twin_b.id)
        ]
        self.assertEqual(len(holding), 1, "one merged group, one tile")

    def test_no_curated_categories_hides_the_tile_row_entirely(self):
        microsite = {"Host": "wsc-panaderia.example"}
        response = self.url_open("/shop", headers=microsite)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("o_wsc_category_tiles_row", response.text)

        self.category.cover_image = TINY_PNG
        response = self.url_open("/shop", headers=microsite)
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wsc_category_tiles_row", response.text)
        self.assertIn("o_wsc_category_tile", response.text)

    def test_active_category_chip_appears_and_clears(self):
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("wsc_category_chip", response.text)

        response = self.url_open("/shop/category/%s" % self.category.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="wsc_category_chip"', response.text)
        self.assertIn(self.category.name, response.text)
        self.assertIn("wd-filter-chip-x", response.text)

    def test_tiles_absent_on_the_aggregated_shops_but_chip_stays(self):
        """The tile row is the merchant's own showcase: a curated
        cover_image shows tiles on the microsite, never on the portal or a
        zone shop. The chip is a way out of a filter and stays everywhere."""
        self.category.cover_image = TINY_PNG
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("o_wsc_category_tiles_row", response.text)

        response = self.url_open("/shop/category/%s" % self.category.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="wsc_category_chip"', response.text)

        response = self.url_open("/shop", headers={"Host": "wsc-panaderia.example"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("o_wsc_category_tiles_row", response.text)
