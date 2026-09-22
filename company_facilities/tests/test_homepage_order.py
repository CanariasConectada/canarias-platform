# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json

from odoo.tests import HttpCase, tagged

from ..models.website import FACILITIES_CALL_MARKER

STRIP_SRC = "/web/image/952/subvenciones.png"


def imported_homepage(key, label):
    """A homepage shaped like the 206 imported from the old platform."""
    return (
        '<t name="Home" t-name="website.homepage_%(key)s">'
        '<t t-call="website.layout">'
        '<div id="wrap" class="oe_structure oe_empty">'
        '<section class="s_cover" data-snippet="s_cover" data-name="Hero">'
        "<h1>%(label)s</h1></section>"
        '<section class="s_kickoff" data-name="Separador"><p>%(label)s</p></section>'
        '<section class="s_website_form pt8" data-snippet="s_website_form" '
        'style="a:b" data-name="Formulario"><h4>CF-CONTACT-SECTION</h4></section>'
        '<section class="s_picture" data-name="Subvenciones">'
        '<img src="%(strip)s" alt="CF-FUNDING-STRIP"/></section>'
        "</div></t></t>"
    ) % {"key": key, "label": label, "strip": STRIP_SRC}


@tagged("post_install", "-at_install")
class TestHomepageOrder(HttpCase):
    """A merchant homepage ends contact, funding strip, footer (2026-09-16)."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Orden de secciones"})
        cls.website = cls.env["website"].create(
            {
                "name": "Orden de secciones",
                "company_id": cls.company.id,
                "domain": "cf-order-test.example",
            }
        )
        cls.company.website_id = cls.website
        category = cls.env["company.facility.category"].create(
            {"name": "CF-Acceso", "icon": "fa-universal-access"}
        )
        cls.facility = cls.env["company.facility"].create(
            {"name": "CF-Rampa", "category_id": category.id}
        )
        cls.page = cls._homepage(cls.website, "cforder")

    @classmethod
    def _homepage(cls, website, key):
        Page = cls.env["website.page"]
        page = Page.search(
            [
                ("website_id", "=", website.id),
                ("url", "=", "/"),
                ("view_id.website_id", "=", website.id),
            ],
            limit=1,
        )
        if not page:
            view = cls.env["ir.ui.view"].create(
                {
                    "name": "Home",
                    "type": "qweb",
                    "key": "website.homepage_%s" % key,
                    "website_id": website.id,
                    "arch": imported_homepage(key, "Hola"),
                }
            )
            page = Page.create(
                {
                    "url": "/",
                    "view_id": view.id,
                    "website_id": website.id,
                    "is_published": True,
                }
            )
        cls._set_archs(
            page.view_id,
            {
                "en_US": imported_homepage(key, "Hello"),
                "es_ES": imported_homepage(key, "Hola"),
            },
        )
        return page

    @classmethod
    def _set_archs(cls, view, archs):
        view.flush_recordset()
        cls.env.cr.execute(
            "UPDATE ir_ui_view SET arch_db = %s::jsonb WHERE id = %s",
            (json.dumps(archs), view.id),
        )
        view.invalidate_recordset(["arch_db"])

    def _archs(self, view):
        view.flush_recordset()
        self.env.cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", (view.id,))
        return self.env.cr.fetchone()[0]

    def test_the_block_goes_before_the_contact_section_in_every_language(self):
        counts = self.website._cf_place_facilities_in_homepage()
        self.assertEqual(counts["updated"], 1)
        archs = self._archs(self.page.view_id)
        self.assertEqual(set(archs), {"en_US", "es_ES"})
        for lang, arch in archs.items():
            call = arch.index(FACILITIES_CALL_MARKER)
            form = arch.index('data-name="Formulario"')
            strip = arch.index('data-name="Subvenciones"')
            self.assertLess(call, form, lang)
            self.assertLess(form, strip, lang)
            self.assertEqual(arch.count("<section"), 4, lang)
            self.assertLess(arch.rindex("<section"), strip, lang)
            self.assertIn('t-value="website.company_id.sudo()"', arch)

    def test_running_it_twice_changes_nothing(self):
        self.website._cf_place_facilities_in_homepage()
        first = self._archs(self.page.view_id)
        counts = self.website._cf_place_facilities_in_homepage()
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(counts["already_there"], 1)
        self.assertEqual(self._archs(self.page.view_id), first)

    def test_a_malformed_arch_is_skipped_in_all_its_languages(self):
        broken = {
            "en_US": imported_homepage("cforder", "Hello"),
            "es_ES": imported_homepage("cforder", "Hola").replace("</div>", "", 1),
        }
        self._set_archs(self.page.view_id, broken)
        counts = self.website._cf_place_facilities_in_homepage()
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(self._archs(self.page.view_id), broken)

    def test_the_first_of_two_contact_sections_gets_the_block(self):
        arch = imported_homepage("cforder", "Hola").replace(
            '<section class="s_website_form',
            '<section data-name="Formulario Contacto"><p>info</p></section>'
            '<section class="s_website_form',
        )
        self._set_archs(self.page.view_id, {"en_US": arch})
        self.website._cf_place_facilities_in_homepage()
        new = self._archs(self.page.view_id)["en_US"]
        self.assertLess(
            new.index(FACILITIES_CALL_MARKER),
            new.index('data-name="Formulario Contacto"'),
        )

    def test_portal_and_zone_websites_are_left_alone(self):
        portal = self.env["website"].browse(1).exists()
        if not portal:
            self.skipTest("no website 1 in this database")
        page = self._homepage(portal, "cfportal")
        before = self._archs(page.view_id)
        self.env["website"]._cf_place_facilities_in_homepage()
        self.assertEqual(self._archs(page.view_id), before)

    def test_the_rendered_homepage_ends_contact_strip_footer(self):
        self.company.facility_ids = self.facility
        self.website._cf_place_facilities_in_homepage()
        response = self.url_open("/", headers={"Host": "cf-order-test.example"})
        self.assertEqual(response.status_code, 200)
        html = response.text
        facilities = html.index('data-name="Facilities"')
        form = html.index("CF-CONTACT-SECTION")
        strip = html.index("CF-FUNDING-STRIP")
        bottom = html.index('id="bottom"')
        self.assertLess(facilities, form)
        self.assertLess(form, strip)
        self.assertLess(strip, bottom)
        self.assertNotIn("o_cf_facilities", html[bottom:])
        self.assertIn("CF-Rampa", html[facilities:form])

    def test_a_shop_that_ticked_nothing_renders_no_block(self):
        self.company.facility_ids = False
        self.website._cf_place_facilities_in_homepage()
        response = self.url_open("/", headers={"Host": "cf-order-test.example"})
        self.assertIn("CF-CONTACT-SECTION", response.text)
        self.assertNotIn("o_cf_facilities", response.text)
