# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user
from odoo.tools import mute_logger

# 1x1 red PNG. Small enough to inline, real enough for image_process.
TINY_PNG = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8"
        "BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
)

SITE_A = "wsmc-alfa.example"
SITE_B = "wsmc-beta.example"


@tagged("post_install", "-at_install")
class TestMerchantCategories(HttpCase):
    """A merchant decorates the category tiles of THEIR shop, and only theirs.

    Asked for on 2026-09-16 with a screenshot of a "Fuentes y volcanes" tile:
    "que los usuarios de comercio tengan su espacio para crear sus categorías
    con imágenes [...] esa imagen solo para su sitio; no quiero que
    modifiquen esto para todos los demás comercios que usan esta categoría".

    Two shops, Alfa and Beta, both selling under the same shared category.
    Whatever Alfa's merchant does must show on Alfa's shop and nowhere else,
    and must never reach the shared category itself.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Category = cls.env["product.public.category"]
        # Shared: no website, the way the 402 migrated categories are.
        cls.shared = Category.create({"name": "Portátiles"})
        cls.shop_a, cls.site_a = cls._shop("WSMC Alfa SL", SITE_A)
        cls.shop_b, cls.site_b = cls._shop("WSMC Beta SL", SITE_B)
        cls.product_a = cls._product("WSMC Portátil Alfa", cls.shop_a, cls.shared)
        cls.product_b = cls._product("WSMC Portátil Beta", cls.shop_b, cls.shared)
        cls.merchant_a = cls._merchant("wsmc_merchant_alfa", cls.shop_a)
        cls.merchant_b = cls._merchant("wsmc_merchant_beta", cls.shop_b)
        cls.both = new_test_user(
            cls.env,
            login="wsmc_merchant_both",
            groups="merchant_group.group_merchant",
            company_id=cls.shop_a.id,
            company_ids=[(6, 0, (cls.shop_a | cls.shop_b).ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    @classmethod
    def _shop(cls, name, domain):
        # auto_microsite_generator would give the company a second site of
        # its own; the suite builds the site whose domain it asserts on.
        company = (
            cls.env["res.company"]
            .with_context(no_microsite_auto=True)
            .create({"name": name})
        )
        website = cls.env["website"].create(
            {"name": name, "company_id": company.id, "domain": "https://" + domain}
        )
        return company, website

    @classmethod
    def _product(cls, name, company, category):
        return cls.env["product.template"].create(
            {
                "name": name,
                "sale_ok": True,
                "is_published": True,
                "list_price": 9.0,
                "company_ids": [(6, 0, company.ids)],
                "public_categ_ids": [(6, 0, category.ids)],
                "website_sequence": 1,
            }
        )

    @classmethod
    def _merchant(cls, login, company):
        return new_test_user(
            cls.env,
            login=login,
            groups="merchant_group.group_merchant",
            company_id=company.id,
            company_ids=[(6, 0, company.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _categories(self, user):
        return self.env["product.public.category"].with_user(user)

    def _tiles(self, user):
        return self.env["website.category.tile"].with_user(user)

    def _shop_page(self, host):
        response = self.url_open("/shop", headers={"Host": host})
        self.assertEqual(response.status_code, 200)
        return response.text

    # ------------------------------------------------------------------
    # The tile on the shop page
    # ------------------------------------------------------------------

    def test_override_image_wins_on_its_own_shop_only(self):
        """Same shared category on both shops: Alfa's picture on Alfa, the
        shared cover everywhere else."""
        self.shared.cover_image = TINY_PNG
        tile = self._tiles(self.merchant_a).create(
            {
                "website_id": self.site_a.id,
                "category_id": self.shared.id,
                "image": TINY_PNG,
            }
        )
        override_url = "/web/image/website.category.tile/%s/image" % tile.id
        shared_url = (
            "/web/image/product.public.category/%s/cover_image" % self.shared.id
        )

        page_a = self._shop_page(SITE_A)
        self.assertIn(override_url, page_a)
        self.assertNotIn(shared_url, page_a)

        page_b = self._shop_page(SITE_B)
        self.assertIn(shared_url, page_b)
        self.assertNotIn(override_url, page_b)

    def test_override_alone_curates_a_tile(self):
        """A shared category nobody gave a cover tiles on the one shop that
        set an image for it, and keeps not tiling on the other."""
        self.assertNotIn("o_wsc_category_tiles_row", self._shop_page(SITE_A))
        self._tiles(self.merchant_a).create(
            {
                "website_id": self.site_a.id,
                "category_id": self.shared.id,
                "image": TINY_PNG,
            }
        )
        self.assertIn("o_wsc_category_tiles_row", self._shop_page(SITE_A))
        self.assertNotIn("o_wsc_category_tiles_row", self._shop_page(SITE_B))

    def test_a_row_without_an_image_curates_nothing(self):
        self._tiles(self.merchant_a).create(
            {"website_id": self.site_a.id, "category_id": self.shared.id}
        )
        self.assertEqual(self.site_a._wsc_shop_category_tiles(), [])

    def test_label_override_is_this_shops_alone(self):
        self.shared.cover_image = TINY_PNG
        self._tiles(self.merchant_a).create(
            {
                "website_id": self.site_a.id,
                "category_id": self.shared.id,
                "image": TINY_PNG,
                "name": "Nuestros portátiles",
            }
        )
        self.assertIn("Nuestros portátiles", self._shop_page(SITE_A))
        self.assertNotIn("Nuestros portátiles", self._shop_page(SITE_B))
        self.assertEqual(self.shared.name, "Portátiles")

    # ------------------------------------------------------------------
    # The shared category stays shared
    # ------------------------------------------------------------------

    def test_merchant_cannot_touch_the_shared_category(self):
        shared = self._categories(self.merchant_a).browse(self.shared.id)
        self.assertEqual(shared.name, "Portátiles", "reading stays open")
        for vals in ({"name": "Mis portátiles"}, {"cover_image": TINY_PNG}):
            with self.subTest(vals=vals), self.assertRaises(AccessError):
                shared.write(vals)
        with self.assertRaises(AccessError):
            shared.unlink()
        self.assertEqual(self.shared.name, "Portátiles")
        self.assertFalse(self.shared.cover_image)

    def test_merchant_cannot_curate_another_shops_tiles(self):
        with self.assertRaises(AccessError):
            self._tiles(self.merchant_a).create(
                {"website_id": self.site_b.id, "category_id": self.shared.id}
            )
        foreign = self._tiles(self.merchant_b).create(
            {"website_id": self.site_b.id, "category_id": self.shared.id}
        )
        with self.assertRaises(AccessError):
            self._tiles(self.merchant_a).browse(foreign.id).write({"image": TINY_PNG})
        with self.assertRaises(AccessError):
            self._tiles(self.merchant_a).browse(foreign.id).unlink()

    def test_one_tile_per_category_and_shop(self):
        self._tiles(self.merchant_a).create(
            {"website_id": self.site_a.id, "category_id": self.shared.id}
        )
        with (
            self.assertRaises(Exception),
            mute_logger("odoo.sql_db"),
            self.env.cr.savepoint(),
        ):
            self._tiles(self.merchant_a).create(
                {"website_id": self.site_a.id, "category_id": self.shared.id}
            )

    def test_a_tile_never_shows_another_shops_own_category(self):
        own_b = self._categories(self.merchant_b).create({"name": "Solo Beta"})
        with self.assertRaises(ValidationError):
            self.env["website.category.tile"].create(
                {"website_id": self.site_a.id, "category_id": own_b.id}
            )

    # ------------------------------------------------------------------
    # Own categories
    # ------------------------------------------------------------------

    def test_merchant_creates_an_own_category_pinned_to_their_site(self):
        """Whatever the form sends, the category lands on the merchant's
        site: another shop's site, no site at all (which would be a shared
        category), or nothing."""
        for sent in ({"website_id": self.site_b.id}, {"website_id": False}, {}):
            with self.subTest(sent=sent):
                category = self._categories(self.merchant_a).create(
                    dict({"name": "Fuentes y volcanes"}, **sent)
                )
                self.assertEqual(category.website_id, self.site_a)

    def test_merchant_edits_and_deletes_their_own_category(self):
        own = self._categories(self.merchant_a).create({"name": "Fuentes y volcanes"})
        own.write({"name": "Fuentes, volcanes y lava", "cover_image": TINY_PNG})
        self.assertEqual(own.name, "Fuentes, volcanes y lava")
        self.assertTrue(own.cover_image)
        own.unlink()
        self.assertFalse(own.exists())

    def test_merchant_cannot_move_their_category_off_their_site(self):
        own = self._categories(self.merchant_a).create({"name": "Fuentes y volcanes"})
        for website_id in (False, self.site_b.id):
            with self.subTest(website_id=website_id), self.assertRaises(AccessError):
                own.write({"website_id": website_id})
        self.assertEqual(own.website_id, self.site_a)

    def test_merchant_cannot_edit_another_shops_own_category(self):
        own_b = self._categories(self.merchant_b).create({"name": "Solo Beta"})
        as_a = self._categories(self.merchant_a).browse(own_b.id)
        with self.assertRaises(AccessError):
            as_a.write({"name": "Ahora de Alfa"})
        with self.assertRaises(AccessError):
            as_a.unlink()
        self.assertEqual(own_b.name, "Solo Beta")

    def test_own_category_hangs_under_an_own_one_or_none(self):
        Category = self._categories(self.merchant_a)
        parent = Category.create({"name": "Naturaleza"})
        child = Category.create({"name": "Volcanes", "parent_id": parent.id})
        self.assertEqual(child.website_id, self.site_a)
        with self.assertRaises(AccessError):
            Category.create({"name": "Bajo compartida", "parent_id": self.shared.id})
        own_b = self._categories(self.merchant_b).create({"name": "Solo Beta"})
        with self.assertRaises(AccessError):
            Category.create({"name": "Bajo ajena", "parent_id": own_b.id})
        with self.assertRaises(AccessError):
            child.write({"parent_id": self.shared.id})

    def test_multi_shop_owner_may_pick_either_of_their_sites(self):
        Category = self._categories(self.both)
        on_b = Category.create({"name": "En Beta", "website_id": self.site_b.id})
        self.assertEqual(on_b.website_id, self.site_b)
        defaulted = Category.create({"name": "Donde toque"})
        self.assertEqual(defaulted.website_id, self.site_a, "the session shop")

    def test_administrators_are_unaffected(self):
        shared = self.env["product.public.category"].create(
            {"name": "Nueva compartida"}
        )
        self.assertFalse(shared.website_id)
        self.shared.write({"cover_image": TINY_PNG, "name": "Portátiles y tablets"})
        self.assertEqual(self.shared.name, "Portátiles y tablets")
        moved = self.env["product.public.category"].create(
            {"name": "Para Beta", "website_id": self.site_b.id}
        )
        moved.write({"website_id": False})
        self.assertFalse(moved.website_id)

    def test_a_user_without_a_shop_cannot_own_a_category(self):
        nobody = new_test_user(
            self.env,
            login="wsmc_no_shop",
            groups="merchant_group.group_merchant",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        with self.assertRaises(UserError):
            self._categories(nobody).create({"name": "Sin tienda"})

    # ------------------------------------------------------------------
    # The screen
    # ------------------------------------------------------------------

    def test_the_screen_opens_on_the_merchants_own_shop(self):
        action = self._tiles(self.merchant_a).action_open_shop_categories()
        self.assertEqual(action["res_model"], "website.category.tile")
        self.assertEqual(action["domain"], [("website_id", "=", self.site_a.id)])
        self.assertEqual(action["context"]["default_website_id"], self.site_a.id)

    def test_an_owner_of_several_shops_gets_the_shop_list(self):
        action = self._tiles(self.both).action_open_shop_categories()
        self.assertEqual(action["res_model"], "website")
        self.assertIn(self.site_a.id, action["domain"][0][2])
        self.assertIn(self.site_b.id, action["domain"][0][2])
        as_both = self.site_b.with_user(self.both)
        self.assertEqual(
            as_both.action_microsite_categories()["domain"],
            [("website_id", "=", self.site_b.id)],
        )

    def test_the_categories_button_refuses_a_site_that_is_not_theirs(self):
        with self.assertRaises(AccessError):
            self.site_b.with_user(self.merchant_a).action_microsite_categories()

    def test_a_new_row_offers_the_shops_categories_and_no_others(self):
        only_b = self.env["product.public.category"].create({"name": "Solo en Beta"})
        self.product_b.public_categ_ids = [(4, only_b.id)]
        own_a = self._categories(self.merchant_a).create({"name": "Fuentes y volcanes"})
        row = self._tiles(self.merchant_a).new({"website_id": self.site_a.id})
        choices = row.allowed_category_ids._origin
        self.assertIn(self.shared, choices)
        self.assertIn(own_a, choices, "own, even without a product yet")
        self.assertNotIn(only_b, choices)

    def test_the_own_categories_screen_shows_only_theirs(self):
        tiles = self._tiles(self.merchant_a).with_context(
            wsmc_website_id=self.site_a.id
        )
        action = tiles.action_own_categories()
        self.assertEqual(action["res_model"], "product.public.category")
        self.assertEqual(action["domain"], [("website_id", "=", self.site_a.id)])
        self.assertEqual(
            tiles.action_new_own_category()["context"]["default_website_id"],
            self.site_a.id,
        )
        with self.assertRaises(AccessError):
            self._tiles(self.merchant_a).with_context(
                wsmc_website_id=self.site_b.id
            ).action_own_categories()

    def test_an_administrator_sees_every_shops_tiles(self):
        """Platform staff with no shop of their own get every shop's tiles
        grouped by site. An administrator proper holds every company on
        this platform (`res_company_admin_sync`), so they get the "My shops"
        list instead, exactly as the "Page content" menu answers them."""
        admin = new_test_user(
            self.env,
            login="wsmc_admin",
            groups="base.group_erp_manager",
            context={"no_reset_password": True, "tracking_disable": True},
        )
        action = self._tiles(admin).action_open_shop_categories()
        self.assertEqual(action["res_model"], "website.category.tile")
        self.assertNotIn("domain", action)
        self.assertEqual(action["context"]["group_by"], "website_id")
        wide = self._tiles(admin).action_own_categories()
        self.assertEqual(wide["domain"], [("website_id", "!=", False)])
        self.assertEqual(
            self.env["website.category.tile"].action_open_shop_categories()[
                "res_model"
            ],
            "website",
        )
