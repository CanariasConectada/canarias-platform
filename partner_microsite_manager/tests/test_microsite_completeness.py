# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import TransactionCase

from .test_homepage_completeness import STATIC_ARCH

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
IMAGES = ["Hero image", "Section 1 image", "Strip 2 image"]
TEXTS = ["Intro title", "About text", "Services text", "Strip 2 title"]


class TestMicrositeCompleteness(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        vals = {
            "name": "Zzmc Complete Shop",
            "street": "Calle Mayor 1",
            "zip": "35010",
            "city": "Las Palmas",
            "phone": "928 00 00 00",
            "email": "shop@example.com",
            "logo": PNG,
            "microsite_opening_hours": "L-V 10:00-14:00",
        }
        Company = cls.env["res.company"].with_context(no_microsite_auto=True)
        if "category_id" in Company._fields:
            category = cls.env[Company._fields["category_id"].comodel_name].create(
                {"name": "Zzmc Bakery"}
            )
            vals["category_id"] = category.id
        cls.company = Company.create(vals)
        cls.website = cls.env["website"].create(
            {"name": "Zzmc Shop", "company_id": cls.company.id}
        )
        cls.attachment = cls.env["ir.attachment"].create(
            {"name": "hero.png", "datas": PNG}
        )

    def _static_page(self, **values):
        attachment_url = f"/web/image/{self.attachment.id}-1a2b/hero.png"
        values = {
            "slug": "zzmc",
            "hero": attachment_url,
            "intro": f"/web/image/res.company/{self.company.id}/microsite_intro_image",
            "strip": "https://example.com/strip.jpg",
            "intro_title": "Bread since 1950",
            "about": "A family bakery.",
            "services": "Bread &amp; cakes.",
            "strip_title": "Fresh every morning",
            **values,
        }
        # As the importer did: the website's own homepage gets its arch.
        page = self.env["website.page"].search(
            [("url", "=", "/"), ("website_id", "=", self.website.id)], limit=1
        )
        vals = {
            "name": "Home",
            "type": "qweb",
            "key": f"website.homepage_{values['slug']}",
            "arch_db": STATIC_ARCH.format(**values),
            "website_id": self.website.id,
        }
        if page:
            page.view_id.write(vals)
        else:
            view = self.env["ir.ui.view"].create(vals)
            self.env["website.page"].create(
                {"url": "/", "view_id": view.id, "website_id": self.website.id}
            )

    def _missing(self):
        self.env.invalidate_all()
        return self.company._get_microsite_missing_items()[self.company.id]

    def test_static_page_complete(self):
        self.company.microsite_intro_image = PNG
        self._static_page()
        self.assertEqual(self._missing(), [])

    def test_static_page_missing_images_and_texts(self):
        dangling = self.attachment.id + 10**8
        self._static_page(
            hero=f"/web/content/{dangling}",
            intro_title="",
            about="",
            services=" ",
            strip_title="CONSUME PRODUCTOS CANARIOS",
        )
        # The intro image points at a company image that is not set.
        self.assertEqual(self._missing(), ["Hero image", "Section 1 image", *TEXTS])

    def test_dynamic_page_reads_company_fields(self):
        self.company._publish_microsite_homepage(self.website)
        self.assertEqual(self._missing(), IMAGES + TEXTS)
        self.company.write(
            {
                "microsite_hero_image": PNG,
                "microsite_intro_image": PNG,
                "microsite_banner_image": PNG,
                "microsite_intro_title": "Bread since 1950",
                "microsite_about_text": "A family bakery.",
                "microsite_services_text": "Bread and cakes.",
                "microsite_banner_title": "Consume Productos Canarios",
            }
        )
        self.assertEqual(self._missing(), ["Strip 2 title"])
        self.company.microsite_banner_title = "Fresh every morning"
        self.assertEqual(self._missing(), [])

    def test_contact_items(self):
        self.company._publish_microsite_homepage(self.website)
        self.company.partner_id.write(
            {"phone": False, "email": False, "street": False, "city": False}
        )
        self.company.write({"logo": False, "microsite_opening_hours": False})
        self.company.partner_id.zip = False
        missing = self._missing()
        for label in ("Logo", "Phone", "Email", "Address", "Opening hours"):
            self.assertIn(label, missing)
