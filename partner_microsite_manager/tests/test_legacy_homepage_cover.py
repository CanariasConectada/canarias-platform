# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64
import importlib.util
import os

from lxml import etree, html

from odoo.tests.common import BaseCase, TransactionCase

from ..tools import legacy_cover, legacy_homepage

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc00000030101007f6a6b8d0000000049454e44ae426082"
)
OTHER_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c636078c1f01f0003040101c9c7e1560000000049454e44ae426082"
)
# Zig Zag Merceria (view 3712, 2026-11-15), trimmed: the cover, the two
# picture strips and a contact block, every value typed in by the importer.
COVER_ARCH = """<t name="Home - {slug}" t-name="website.homepage_{slug}">
<div id="wrap" class="oe_structure oe_empty">
<section class="s_cover" data-snippet="s_cover" data-name="Hero" style="background-image: url('/web/image/ir.attachment/{hero}/datas'); background-size: cover; min-height: 60vh;">
<div class="container"><h1 class="display-1"><span class="display-4-fs">Zig Zag Merceria</span></h1>
<p style="text-align: center;"><a class="btn btn-lg btn-primary o_translate_inline" href="/shop">Store</a></p>
</div></section>
<section class="s_kickoff" data-name="SEC1" style="background-image: url(&quot;/web/image/ir.attachment/{intro}/datas&quot;);"><div class="container"><h2>Ideas and materials</h2></div></section>
<section class="s_attributes_vertical" data-name="Acerca"><p>Our story</p></section>
<section class="s_kickoff" data-name="Separador" style="background-image: url('/web/image/ir.attachment/{strip}/datas');"><div class="container"><h2>Fabrics and threads</h2></div></section>
<section class="s_website_form pt48 pb48" data-snippet="s_website_form" data-name="Formulario">
<div class="container"><div class="row"><div class="col-lg-6">
<p class="mb-2"><i class="fa fa-phone fa-fw mr-2 text-primary"/>928 00 00 00</p>
</div></div></div>
</section>
</div>
</t>"""
# The button as each language copy shows it on prod.
BUTTON = {
    "en_US": "Store",
    "es_ES": "Tienda",
    "de_DE": "Ladengeschäft",
    "fr_FR": "Magasiner",
    "it_IT": "Negozio",
    "pl_PL": "Sklep",
    "pt_PT": "Loja",
}


class TestLegacyHomepageCover(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        for code in BUTTON:
            cls.env["res.lang"]._activate_lang(code)
        cls.company = cls.env["res.company"].create(
            {
                "name": "Zig Zag Merceria",
                "microsite_button_text": "Tienda",
                "microsite_intro_title": "Ideas and materials",
                "microsite_banner_title": "Fabrics and threads",
                "microsite_hero_image": base64.b64encode(PNG),
                "microsite_intro_image": base64.b64encode(PNG),
                "microsite_banner_image": base64.b64encode(PNG),
            }
        )
        cls.website = cls.env["website"].create(
            {"name": "Zig Zag", "company_id": cls.company.id}
        )
        cls.website.language_ids = cls.env["res.lang"].search(
            [("code", "in", list(BUTTON))]
        )
        cls.website.default_lang_id = cls.env.ref("base.lang_es")

    def _attachment(self, raw=PNG):
        return self.env["ir.attachment"].create(
            {"name": "imported.png", "raw": raw, "public": True}
        )

    def _page(self, slug="zigzag", key=None, hero=None):
        hero = hero or self._attachment()
        arch = COVER_ARCH.format(
            slug=slug,
            hero=hero.id,
            intro=self._attachment().id,
            strip=self._attachment().id,
        )
        view = self.env["ir.ui.view"].create(
            {
                "name": f"Home - {slug}",
                "type": "qweb",
                "key": key or f"website.homepage_{slug}",
                "arch_db": arch,
                "website_id": self.website.id,
            }
        )
        self.env["website.page"].create(
            {
                "name": f"Home - {slug}",
                "url": "/",
                "view_id": view.id,
                "website_id": self.website.id,
                "is_published": True,
            }
        )
        # Seven copies, identical but for the button, as on prod.
        for code, word in BUTTON.items():
            if code != "en_US":
                self.env.cr.execute(
                    "UPDATE ir_ui_view SET arch_db = arch_db || "
                    "jsonb_build_object(%s, %s::text) WHERE id = %s",
                    [code, arch.replace(">Store<", f">{word}<"), view.id],
                )
        view.invalidate_recordset()
        return view

    def _raw(self, view):
        return self.env["res.company"]._get_arch_db_raw(view)

    def _render(self, view, lang="es_ES", **values):
        values["website"] = self.website
        return str(self.env["ir.qweb"].with_context(lang=lang)._render(view.id, values))

    def _module(self, version):
        folder = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations",
            version,
        )
        # 19.0.2.13.0 is a post- script, 19.0.2.20.0 an end- script.
        path = next(
            os.path.join(folder, name)
            for name in ("end-migration.py", "post-migration.py")
            if os.path.exists(os.path.join(folder, name))
        )
        spec = importlib.util.spec_from_file_location(f"pmm_{version}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _migrate(self):
        self._module("19.0.2.20.0").migrate(self.env.cr, "19.0.2.19.0")

    def _cover_stat(self, view):
        # As the migration does: back the page up first (an edit or a
        # builder save only relinks pages that were backed up).
        self._module("19.0.2.20.0")._backup_arch(self.env, view.id)
        [stat] = self.env["res.company"]._relink_legacy_homepage_live_data(
            views=view, mode="cover"
        )
        return stat

    # -- the migration ---------------------------------------------------
    def test_the_button_follows_the_editor_in_every_language(self):
        view = self._page()
        self._migrate()
        self.company.write({"microsite_button_text": "Productos"})
        for code in BUTTON:
            page = self._render(view, lang=code)
            self.assertIn("Productos", page, code)
            self.assertIn('href="/shop"', page)
            for word in BUTTON.values():
                self.assertNotIn(f">{word}<", page, code)
        raw = self._raw(view)
        for code in BUTTON:
            self.assertIn(legacy_homepage.LIVE_TEMPLATES["button"], raw[code], code)

    def test_an_emptied_field_after_the_relink(self):
        """The page keeps a sensible cover: the button falls back to the
        translated "Shop", an emptied strip title shows nothing."""
        view = self._page()
        self._migrate()
        self.company.write(
            {"microsite_button_text": False, "microsite_banner_title": False}
        )
        # The module's own translations are not loaded here: the source.
        page = self._render(view, lang="en_US")
        self.assertIn('contenteditable="false">Shop<', page)
        self.assertNotIn("Fabrics and threads", page)

    def test_a_multi_company_write_relinks_only_what_changed(self):
        view = self._page()
        self._module("19.0.2.20.0")._backup_arch(self.env, view.id)
        other = self.env["res.company"].create(
            {"name": "Other", "microsite_button_text": "Productos"}
        )
        before = self._raw(view)
        (self.company | other).write({"microsite_button_text": "Tienda"})
        self.assertEqual(self._raw(view), before)

    def test_the_cover_follows_the_company(self):
        view = self._page()
        stat = self._cover_stat(view)
        self.assertTrue(stat["written"])
        self.assertFalse(stat["skipped"])
        self.company.write(
            {
                "microsite_name": "Zig Zag",
                "microsite_intro_title": "New intro",
                "microsite_banner_title": "New strip",
            }
        )
        page = self._render(view)
        for value in ("Zig Zag<", "New intro", "New strip", "Our story"):
            self.assertIn(value, page)
        for kind, (_slot, field) in legacy_cover.IMAGE_KINDS.items():
            self.assertIn(f"/web/image/res.company/{self.company.id}/{field}", page)
        self.assertNotIn("ir.attachment", page)
        # Every other text of every language copy is kept.
        self.assertIn("Our story", self._raw(view)["de_DE"])

    def test_an_empty_field_keeps_the_typed_text(self):
        self.company.write(
            {"microsite_button_text": False, "microsite_intro_title": False}
        )
        view = self._page()
        stat = self._cover_stat(view)
        kept = {k["kind"]: k["reason"] for k in stat["kept_static"]}
        self.assertEqual(kept["button"], "live_empty")
        self.assertEqual(kept["intro_title"], "live_empty")
        page = self._render(view)
        self.assertIn(">Tienda<", page)
        self.assertIn("Ideas and materials", page)
        # Emptying a field later is no edit to relink either.
        self.company.write({"microsite_banner_title": ""})
        self.assertIn("Tienda", self._raw(view)["es_ES"])

    def test_a_different_title_is_kept_for_the_owner(self):
        self.company.microsite_name = "Another cover title"
        view = self._page()
        stat = self._cover_stat(view)
        self.assertIn(
            {
                "kind": "title",
                "shown": "Zig Zag Merceria",
                "live": "Another cover title",
                "reason": "differs",
            },
            stat["kept_static"],
        )
        self.assertIn("Zig Zag Merceria", self._render(view))
        # A person typing the title makes it live.
        self.company.write({"microsite_name": "Typed by the merchant"})
        self.assertIn("Typed by the merchant", self._render(view))

    def test_another_picture_is_kept(self):
        hero = self._attachment(OTHER_PNG)
        view = self._page(hero=hero)
        stat = self._cover_stat(view)
        self.assertIn("image_differs", {k["reason"] for k in stat["kept_static"]})
        self.assertIn(f"/web/image/ir.attachment/{hero.id}/datas", view.arch_db)
        # A new upload is a human edit: the company picture wins.
        self.company.write({"microsite_hero_image": base64.b64encode(OTHER_PNG)})
        self.assertNotIn(f"ir.attachment/{hero.id}/", view.arch_db)

    def test_the_migration_is_idempotent(self):
        view = self._page()
        self._migrate()
        after = self._raw(view)
        self._migrate()
        self.assertEqual(self._raw(view), after)
        self.assertEqual(
            self.env["ir.attachment"].search_count(
                [
                    ("res_model", "=", "ir.ui.view"),
                    ("res_id", "=", view.id),
                    ("name", "like", "-19.0.2.20.0.json"),
                ]
            ),
            1,
        )

    def test_dynamic_homepages_are_not_touched(self):
        view = self._page(
            slug="dynamic",
            key=f"partner_microsite_manager.microsite_homepage_{self.company.id}",
        )
        before = self._raw(view)
        self._migrate()
        self.assertEqual(self._raw(view), before)

    def test_an_edit_relinks_a_page_the_cover_migration_never_saw(self):
        view = self._page()
        self._module("19.0.2.13.0")._backup_arch(self.env, view.id)
        self.company.write({"microsite_button_text": "Productos"})
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["button"], view.arch_db)
        self.assertIn("Productos", self._render(view, lang="de_DE"))

    def test_a_builder_save_keeps_the_cover_live(self):
        view = self._page()
        self._migrate()
        rendered = html.fromstring(self._render(view, editable=True))
        wrap = rendered.xpath("//div[@id='wrap']")[0]
        view.with_context(website_id=self.website.id).save(
            etree.tostring(wrap, encoding="unicode", method="html"),
            xpath="/t/div",
        )
        for kind in legacy_cover.TEXT_KINDS:
            self.assertIn(legacy_homepage.LIVE_TEMPLATES[kind], view.arch_db)
        self.company.microsite_button_text = "Ofertas"
        self.assertIn("Ofertas", self._render(view))


class TestLegacyCoverTransform(BaseCase):
    def test_a_wrapped_heading_is_relinked_and_markup_is_kept(self):
        arch = (
            '<t><section data-name="SEC1"><h2><font style="color: red">Intro</font>'
            '</h2></section><section data-name="Hero"><h1>Name<br/>Tagline</h1>'
            "</section></t>"
        )
        new, report = legacy_cover.relink_cover(arch, ("intro_title", "title"))
        self.assertEqual(report["relinked"], ["intro_title"])
        self.assertIn("title with markup kept as typed", report["notes"])
        self.assertIn('<font style="color: red"><t t-call=', new)
        self.assertIn("Name<br/>Tagline", new)
        self.assertIsNone(legacy_cover.relink_cover(new, ("intro_title",))[0])

    def test_several_shop_links_are_left_as_typed(self):
        arch = (
            '<t><section data-name="Hero"><p><a class="btn" href="/shop">Shop</a>'
            '<a class="btn" href="/shop">More</a></p><a href="/shop">text</a>'
            "</section></t>"
        )
        self.assertIsNone(legacy_cover.relink_cover(arch, ("button",))[0])
        single = arch.replace('<a class="btn" href="/shop">More</a>', "")
        new, report = legacy_cover.relink_cover(single, ("button",))
        self.assertEqual(report["relinked"], ["button"])
        self.assertIn('<a href="/shop">text</a>', new)
