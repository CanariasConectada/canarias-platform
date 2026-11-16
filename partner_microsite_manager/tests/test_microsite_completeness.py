# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.tests.common import TransactionCase

from .test_homepage_completeness import STATIC_ARCH

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
IMAGES = ["hero", "intro", "strip"]
TEXTS = ["intro_title", "about", "services", "strip_title"]
FILLED = {
    "microsite_hero_image": PNG,
    "microsite_intro_image": PNG,
    "microsite_banner_image": PNG,
    "microsite_intro_title": "Bienvenidos a Zzmc Shop",
    "microsite_about_text": "A family bakery.",
    "microsite_services_text": "Bread and cakes.",
    "microsite_banner_title": "Fresh every morning",
}


class TestMicrositeCompleteness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls._company("Zzmc Shop")
        cls.website = cls.env["website"].create(
            {"name": "Zzmc Shop", "company_id": cls.company.id}
        )
        cls.attachment = cls.env["ir.attachment"].create(
            {
                "name": "hero.png",
                "datas": PNG,
                "res_model": "res.company",
                "res_id": cls.company.id,
            }
        )

    @classmethod
    def _company(cls, name, **vals):
        """A shop with every contact item filled in."""
        Company = cls.env["res.company"].with_context(no_microsite_auto=True)
        vals = {
            "name": name,
            "street": "Calle Mayor 1",
            "zip": "35010",
            "city": "Las Palmas",
            "phone": "928 00 00 00",
            "email": "shop@example.com",
            "logo": PNG,
            "microsite_opening_hours": "L-V 10:00-14:00",
            **vals,
        }
        if "category_id" in Company._fields:
            category = cls.env[Company._fields["category_id"].comodel_name].create(
                {"name": f"Zzmc {name}"}
            )
            vals["category_id"] = category.id
        return Company.create(vals)

    def _page(self, website=None, key="website.homepage_zzmc", **values):
        """Give the website's own homepage an importer arch (as the
        importer did) and return the page."""
        website = website or self.website
        values = {
            "slug": "zzmc",
            "hero": f"/web/image/{self.attachment.id}-1a2b/hero.png",
            "intro": f"/web/image/res.company/{website.company_id.id}/"
            "microsite_intro_image",
            "strip": "https://example.com/strip.jpg",
            "intro_title": "Bienvenidos a Zzmc Shop",
            "about": "A family bakery.",
            "services": "Bread &amp; cakes.",
            "strip_title": "Fresh every morning",
            **values,
        }
        vals = {
            "name": "Home",
            "type": "qweb",
            "key": key,
            "arch_db": STATIC_ARCH.format(**values),
            "website_id": website.id,
        }
        page = self.env["website.page"].search(
            [("url", "=", "/"), ("website_id", "=", website.id)], limit=1
        )
        if page:
            page.view_id.write(vals)
            return page
        view = self.env["ir.ui.view"].create(vals)
        return self.env["website.page"].create(
            {"url": "/", "view_id": view.id, "website_id": website.id}
        )

    def _missing(self, company=None):
        company = company or self.company
        self.env.invalidate_all()
        return company._get_microsite_missing_items()[company.id]

    def test_static_page_complete(self):
        self.company.microsite_intro_image = PNG
        self._page()
        self.assertEqual(self._missing(), [])

    def test_static_page_gaps(self):
        dangling = self.attachment.id + 10**8
        self._page(
            hero=f"/web/content/{dangling}",
            intro_title="",
            about="",
            services=" ",
            strip_title="CONSUME PRODUCTOS CANARIOS",
        )
        # The intro image points at a company image that is not set.
        self.assertEqual(self._missing(), ["hero", "intro", *TEXTS])

    def test_dangling_image_in_portada_section(self):
        self.company.microsite_intro_image = PNG
        page = self._page(hero=f"/web/content/{self.attachment.id + 10**8}")
        arch = page.view_id.arch_db.replace('data-name="Hero"', 'data-name="Portada"')
        page.view_id.arch_db = arch
        self.assertEqual(self._missing(), ["hero"])

    def test_image_urls_must_be_the_shops(self):
        self.company.microsite_intro_image = PNG
        other = self._company("Zzmc Other")
        foreign = self.attachment.copy({"res_id": other.id})
        self._page(
            hero=f"/web/image/ir.attachment/{foreign.id}/datas",
            intro=f"/web/image/res.partner/{other.partner_id.id}/image_1920",
            strip="/web/image/website.s_cover_default_image",
        )
        self.assertEqual(self._missing(), IMAGES)
        foreign.public = True
        own_logo = f"/web/image/res.partner/{self.company.partner_id.id}/image_1920"
        self._page(hero=f"/web/image/ir.attachment/{foreign.id}/datas", intro=own_logo)
        self.assertEqual(self._missing(), [])

    def test_placeholders_count_as_missing(self):
        self.company.write(FILLED)
        self.company._publish_microsite_homepage(self.website)
        self.assertEqual(self._missing(), [], "'Bienvenidos a <shop>' is kept")
        placeholders = {
            "microsite_intro_title": "Descubre lo que tenemos para ti",
            "microsite_about_text": "En nuestro espacio encontrarás productos y "
            "servicios seleccionados con dedicación. Visítanos.",
            "microsite_services_text": "Atención cercana y asesoramiento honesto "
            "sobre lo que ofrecemos.",
            "microsite_banner_title": "consume productos canarios",
        }
        self.company.write(placeholders)
        self.assertEqual(self._missing(), TEXTS)
        self.company.microsite_intro_title = "Bienvenidos a nuestro espacio."
        self.assertIn("intro_title", self._missing())

    def test_dynamic_page_reads_company_fields(self):
        self.company._publish_microsite_homepage(self.website)
        self.assertEqual(self._missing(), IMAGES + TEXTS)
        self.company.write(FILLED)
        self.assertEqual(self._missing(), [])

    def test_company_without_website(self):
        company = self._company("Zzmc No Site", **FILLED)
        self.assertEqual(self._missing(company), ["homepage"])

    def test_page_choice(self):
        """The published microsite page wins over the lowest website."""
        self.company.microsite_intro_image = PNG
        self._page(about="")
        second = self.env["website"].create(
            {"name": "Zzmc Shop 2", "company_id": self.company.id}
        )
        published = self._page(website=second, key="website.homepage_zzmc2")
        self.assertEqual(self._missing(), ["about"], "lowest website id")
        self.company.microsite_homepage_page_id = published
        self.assertEqual(self._missing(), [])

    def test_custom_page_is_checked_by_hand(self):
        self._page(key="theme_corporate_multi.homepage", hero="", intro_title="")
        self.assertEqual(self._missing(), ["custom_page"])
        self.company.logo = False
        self.assertEqual(self._missing(), ["custom_page", "logo"])

    def test_spanish_arch_counts(self):
        self.env["res.lang"]._activate_lang("es_ES")
        self.company.microsite_intro_image = PNG
        page = self._page()
        spanish = STATIC_ARCH.format(
            slug="zzmc",
            hero=f"/web/image/{self.attachment.id}",
            intro=f"/web/image/res.company/{self.company.id}/microsite_intro_image",
            strip="https://example.com/strip.jpg",
            intro_title="",
            about="Una panadería familiar.",
            services="Pan y pasteles.",
            strip_title="Recién hecho cada mañana",
        )
        self.env.flush_all()
        self.env.cr.execute(
            "UPDATE ir_ui_view SET arch_db = arch_db || %s::jsonb WHERE id = %s",
            (json.dumps({"es_ES": spanish}), page.view_id.id),
        )
        self.assertEqual(self._missing(), ["intro_title"])

    def test_contact_items(self):
        self.company._publish_microsite_homepage(self.website)
        self.company.partner_id.write(
            {"phone": False, "email": False, "street": False, "city": False}
        )
        self.company.write({"logo": False, "microsite_opening_hours": False})
        self.company.partner_id.zip = False
        missing = self._missing()
        for code in ("logo", "phone", "email", "address", "hours"):
            self.assertIn(code, missing)
