# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Where the certification seals sit on a merchant homepage.

Facilities, seals, contact section, funding strip, footer (client request,
2026-09-21). The seals used to hang off ``website.layout`` above the footer,
after the funding strip; merchant homepages now call the block themselves and
the layout-level section is only the fallback for every other homepage.
"""
import json

from odoo.tests import HttpCase, tagged

from ..models.website import SEALS_CALL_MARKER
from .common import CertificationCase

HOST = "cc-seals-test.example"
STRIP_SRC = "/web/image/952/subvenciones.png"
FACILITIES_MARKER = "company_facilities.facilities_block"
# What ``company_facilities`` left in the imported homepages. Only text here:
# this module does not depend on it, the arch is all the two have in common.
FACILITIES_SNIPPET = (
    '<t t-set="cf_company" t-value="website.company_id.sudo()"/>'
    '<t t-call="company_facilities.facilities_block"/>\n'
)
SEALS_SECTION = 'data-name="Certification Seals"'


def imported_homepage(key, label, facilities=""):
    """A homepage shaped like the 206 imported from the old platform."""
    return (
        '<t name="Home" t-name="website.homepage_%(key)s">'
        '<t t-call="website.layout">'
        '<div id="wrap" class="oe_structure oe_empty">'
        '<section class="s_cover" data-snippet="s_cover" data-name="Hero">'
        "<h1>%(label)s</h1></section>"
        '<section class="s_kickoff" data-name="Separador"><p>%(label)s</p></section>'
        "%(facilities)s"
        '<section class="s_website_form pt8" data-snippet="s_website_form" '
        'style="a:b" data-name="Formulario"><h4>CC-CONTACT-SECTION</h4></section>'
        '<section class="s_text_block" data-name="Texto">'
        "<h4>ENCUENTRANOS</h4></section>"
        '<section class="s_picture" data-name="Subvenciones">'
        '<img src="%(strip)s" alt="CC-FUNDING-STRIP"/></section>'
        "</div></t></t>"
    ) % {"key": key, "label": label, "strip": STRIP_SRC, "facilities": facilities}


@tagged("post_install", "-at_install")
class TestSealsHomepageOrder(CertificationCase, HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Website = cls.env["website"]
        cls.website = Website.search([("company_id", "=", cls.company.id)], limit=1)
        if not cls.website:
            cls.website = Website.create(
                {"name": "Certified Shop", "company_id": cls.company.id}
            )
        cls.website.domain = HOST
        if "website_id" in cls.company._fields:
            cls.company.website_id = cls.website
        cls.page = cls._homepage(cls.website, "ccseals")

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
                "en_US": imported_homepage(key, "Hello", FACILITIES_SNIPPET),
                "es_ES": imported_homepage(key, "Hola", FACILITIES_SNIPPET),
                "de_DE": imported_homepage(key, "Hallo", FACILITIES_SNIPPET),
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
        cls.env.registry.clear_cache("templates")

    def _archs(self, view):
        view.flush_recordset()
        self.env.cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", (view.id,))
        return self.env.cr.fetchone()[0]

    def _award_seal(self, company=None):
        return self.env["res.company.certification"].create(
            {
                "company_id": (company or self.company).id,
                "type_id": self.cert_type.id,
                "level": "gold",
                "score": 100,
                "expiry_date": "2099-01-01",
            }
        )

    def _renderable_archs(self):
        """The fixture without the facilities call when that module is absent:
        an arch is only text, a render needs the template to exist."""
        if self.env.ref(FACILITIES_MARKER, raise_if_not_found=False):
            return
        self._set_archs(
            self.page.view_id, {"en_US": imported_homepage("ccseals", "Hello")}
        )

    def _get_home(self):
        response = self.url_open("/", headers={"Host": HOST})
        self.assertEqual(response.status_code, 200)
        return response.text

    # ------------------------------------------------------------------
    # The arch
    # ------------------------------------------------------------------
    def test_the_call_goes_between_facilities_and_contact_in_every_language(self):
        counts = self.website._cc_place_seals_in_homepage()
        self.assertEqual(counts["updated"], 1)
        archs = self._archs(self.page.view_id)
        self.assertEqual(set(archs), {"en_US", "es_ES", "de_DE"})
        for lang, arch in archs.items():
            facilities = arch.index(FACILITIES_MARKER)
            seals = arch.index(SEALS_CALL_MARKER)
            form = arch.index('data-name="Formulario"')
            strip = arch.index('data-name="Subvenciones"')
            self.assertLess(facilities, seals, lang)
            self.assertLess(seals, form, lang)
            self.assertLess(form, strip, lang)
            self.assertEqual(arch.count(SEALS_CALL_MARKER), 1, lang)
            self.assertEqual(arch.count("<section"), 5, lang)
        # Each language kept its own text.
        self.assertIn("Hello", archs["en_US"])
        self.assertIn("Hola", archs["es_ES"])
        self.assertIn("Hallo", archs["de_DE"])

    def test_a_homepage_without_facilities_still_gets_it_before_contact(self):
        self._set_archs(
            self.page.view_id, {"en_US": imported_homepage("ccseals", "Hello")}
        )
        self.website._cc_place_seals_in_homepage()
        arch = self._archs(self.page.view_id)["en_US"]
        self.assertLess(
            arch.index(SEALS_CALL_MARKER), arch.index('data-name="Formulario"')
        )

    def test_running_it_twice_changes_nothing(self):
        self.website._cc_place_seals_in_homepage()
        first = self._archs(self.page.view_id)
        counts = self.website._cc_place_seals_in_homepage()
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(counts["already_there"], 1)
        self.assertEqual(self._archs(self.page.view_id), first)

    def test_a_malformed_arch_is_skipped_in_all_its_languages(self):
        broken = {
            "en_US": imported_homepage("ccseals", "Hello"),
            "es_ES": imported_homepage("ccseals", "Hola").replace("</div>", "", 1),
        }
        self._set_archs(self.page.view_id, broken)
        counts = self.website._cc_place_seals_in_homepage()
        self.assertEqual(counts["skipped"], 1)
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(self._archs(self.page.view_id), broken)

    def test_a_language_without_contact_section_leaves_the_page_alone(self):
        uneven = {
            "en_US": imported_homepage("ccseals", "Hello"),
            "es_ES": imported_homepage("ccseals", "Hola").replace(
                'data-name="Formulario"', 'data-name="Otro"'
            ),
        }
        self._set_archs(self.page.view_id, uneven)
        counts = self.website._cc_place_seals_in_homepage()
        self.assertEqual(counts["no_contact"], 1)
        self.assertEqual(counts["updated"], 0)
        self.assertEqual(self._archs(self.page.view_id), uneven)

    def test_the_first_of_two_contact_sections_gets_the_call(self):
        arch = imported_homepage("ccseals", "Hola").replace(
            '<section class="s_website_form',
            '<section data-name="Formulario Contacto"><p>info</p></section>'
            '<section class="s_website_form',
        )
        self._set_archs(self.page.view_id, {"en_US": arch})
        self.website._cc_place_seals_in_homepage()
        new = self._archs(self.page.view_id)["en_US"]
        self.assertLess(
            new.index(SEALS_CALL_MARKER),
            new.index('data-name="Formulario Contacto"'),
        )

    def test_portal_and_zone_websites_are_left_alone(self):
        found = False
        for website_id in (1, 12, 13, 14):
            website = self.env["website"].browse(website_id).exists()
            if not website:
                continue
            found = True
            page = self._homepage(website, "ccskip%s" % website_id)
            before = self._archs(page.view_id)
            self.env["website"]._cc_place_seals_in_homepage()
            website._cc_place_seals_in_homepage()
            self.assertEqual(self._archs(page.view_id), before, website_id)
        if not found:
            self.skipTest("no portal or zone website in this database")

    # ------------------------------------------------------------------
    # The rendered page
    # ------------------------------------------------------------------
    def test_the_rendered_homepage_reads_seals_contact_strip_footer(self):
        self._award_seal()
        self._renderable_archs()
        self.website._cc_place_seals_in_homepage()
        html = self._get_home()
        seals = html.index(SEALS_SECTION)
        form = html.index("CC-CONTACT-SECTION")
        strip = html.index("CC-FUNDING-STRIP")
        bottom = html.index('id="bottom"')
        self.assertLess(seals, form)
        self.assertLess(form, strip)
        self.assertLess(strip, bottom)
        # Once: the layout-level section is silent on this page.
        self.assertEqual(html.count(SEALS_SECTION), 1)
        self.assertIn("Test Certification", html[seals:form])

    def test_the_rendered_seals_follow_the_facilities(self):
        if "facility_ids" not in self.company._fields:
            self.skipTest("company_facilities is not installed")
        facility = self.env["company.facility"].search([], limit=1)
        if not facility:
            self.skipTest("no facility in the catalogue")
        self.company.facility_ids = facility
        self._award_seal()
        self.website._cc_place_seals_in_homepage()
        html = self._get_home()
        self.assertLess(html.index('data-name="Facilities"'), html.index(SEALS_SECTION))
        self.assertLess(html.index(SEALS_SECTION), html.index("CC-CONTACT-SECTION"))

    def test_a_shop_without_seals_renders_no_section(self):
        self._renderable_archs()
        self.website._cc_place_seals_in_homepage()
        html = self._get_home()
        self.assertIn("CC-CONTACT-SECTION", html)
        self.assertNotIn(SEALS_SECTION, html)
        self.assertNotIn("o_cc_seals", html)

    def test_an_expired_seal_renders_no_section(self):
        self._award_seal().expiry_date = "2020-01-01"
        self._renderable_archs()
        self.website._cc_place_seals_in_homepage()
        self.assertNotIn(SEALS_SECTION, self._get_home())

    def test_a_homepage_not_calling_the_block_keeps_the_layout_section(self):
        """Portal, zone sites, homepages with no contact section: unchanged."""
        self._award_seal()
        self._set_archs(
            self.page.view_id,
            {
                "en_US": imported_homepage("ccseals", "Hello").replace(
                    'data-name="Formulario"', 'data-name="Otro"'
                )
            },
        )
        counts = self.website._cc_place_seals_in_homepage()
        self.assertEqual(counts["no_contact"], 1)
        html = self._get_home()
        self.assertEqual(html.count(SEALS_SECTION), 1)
        self.assertLess(html.index("CC-FUNDING-STRIP"), html.index(SEALS_SECTION))
        self.assertLess(html.index(SEALS_SECTION), html.index('id="bottom"'))

    def test_other_pages_of_the_shop_show_no_seals(self):
        self._award_seal()
        self._renderable_archs()
        self.website._cc_place_seals_in_homepage()
        response = self.url_open("/contactus", headers={"Host": HOST})
        self.assertNotIn(SEALS_SECTION, response.text)

    def test_the_dynamic_microsite_homepage_places_the_seals_itself(self):
        """Homepages built by ``partner_microsite_manager`` (new microsites)."""
        if not hasattr(self.company, "_publish_microsite_homepage"):
            self.skipTest("partner_microsite_manager is not installed")
        if not hasattr(self.website, "_pmm_certification_block_template"):
            self.skipTest("partner_microsite_manager predates the seals hook")
        self._award_seal()
        self.company.microsite_about_text = "CC-ABOUT-TEXT"
        # Before the only fetch: the rendered homepage is cached per website.
        with_facilities = False
        if "facility_ids" in self.company._fields:
            facility = self.env["company.facility"].search([], limit=1)
            self.company.facility_ids = facility
            with_facilities = bool(facility)
        self.company._publish_microsite_homepage(self.website)
        counts = self.website._cc_place_seals_in_homepage()
        self.assertEqual(counts["dynamic"], 1)
        self.assertEqual(counts["updated"], 0)
        html = self._get_home()
        about = html.index("CC-ABOUT-TEXT")
        seals = html.index(SEALS_SECTION)
        contact = html.index('data-name="Contact"')
        strip = html.index('data-name="Subvenciones"')
        self.assertLess(about, seals)
        self.assertLess(seals, contact)
        self.assertLess(contact, strip)
        self.assertLess(strip, html.index('id="bottom"'))
        self.assertEqual(html.count(SEALS_SECTION), 1)
        if with_facilities:
            facilities = html.index('data-name="Facilities"')
            self.assertLess(about, facilities)
            self.assertLess(facilities, seals)
