# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
import json
import logging
import os
from unittest.mock import patch

from lxml import etree, html

from odoo.tests.common import TransactionCase

from ..tools import legacy_homepage

# The shape the 2026 importer gave ~188 homepages (Panambi, view 3897),
# anonymised and trimmed to the blocks that matter here.
STANDARD_ARCH = """<t name="Home - {slug}" t-name="website.homepage_{slug}">
<div id="wrap" class="oe_structure oe_empty">
<section class="s_cover" data-snippet="s_cover" data-name="Hero"><h1>{slug}</h1></section>
<section class="s_features pt48 pb48" data-snippet="s_features" data-name="Horario">
<div class="container"><div class="row justify-content-center">
<div class="col-lg-4 pt16 pb16 text-center">
<span class="fa fa-clock-o fa-2x mb-3"/><h5 class="fw-bold">Time</h5>
<t t-call="partner_microsite_manager.microsite_opening_hours_card"/>
</div><div class="col-lg-4 pt16 pb16 text-center">
<span class="fa fa-map-marker fa-2x mb-3"/><h5 class="fw-bold">Parking</h5>
<p class="text-muted">Parking nearby</p>
</div><div class="col-lg-4 pt16 pb16 text-center">
<span class="fa fa-truck fa-2x mb-3"/><h5 class="fw-bold">Delivery / Shipping</h5>
<p class="text-muted">Delivery available</p>
</div>
</div></div>
</section>
<section class="s_attributes_vertical" data-name="Acerca"><p>Our story</p></section>
<section class="s_website_form pt48 pb48" data-snippet="s_website_form" data-name="Formulario">
<div class="container"><div class="row">
<div class="col-lg-6 pb16"><h4>WRITE TO US</h4></div>
<div class="col-lg-6">
<div class="mt-3 mb-3"><iframe src="https://maps.google.com/maps?q=Old+Street&amp;output=embed" width="100%" height="200" style="border:0; border-radius: 8px;"/></div>
<h4 class="mb-3"><span class="fa fa-map-marker"/><strong>FIND US.</strong></h4>
<p class="mb-2"><i class="fa fa-map-marker fa-fw mr-2 text-primary"/>Old Town</p>
<p class="mb-2"><i class="fa fa-phone fa-fw mr-2 text-primary"/>928 00 00 00</p>
<p class="mb-2"><i class="fa fa-envelope fa-fw mr-2 text-primary"/>old @ example.com</p>
</div>
</div></div>
</section>
</div>
</t>"""

# Hand-built page (Diaz Leja, view 4911, simplified): no "Horario"
# section, no phone line, contact lines beside a nested form.
CUSTOM_ARCH = """<t name="Home - {slug}" t-name="website.homepage_{slug}">
<div id="wrap" class="oe_structure oe_empty">
<section class="s_kickoff" data-name="SEC1"><h2>Intro</h2></section>
<section class="s_attributes_vertical" data-name="Acerca"><p>About the shop</p></section>
<section class="s_website_form_info" data-name="Formulario Contacto">
<div class="container"><div class="row">
<div class="col-lg-6"><section class="s_website_form" data-name="Formulario"><form/></section></div>
<div class="col-lg-6">
<p class="mb-1"><i class="fa fa-map-marker fa-fw mr-2"/>Calle Vieja 23&amp;nbsp;35010, 35010 Las Palmas</p>
<p class="mb-1"><i class="fa fa-envelope fa-fw mr-2"/>old@example.com</p>
<div class="mt-3"><iframe src="https://maps.google.com/maps?q=Calle+Vieja&amp;output=embed" width="100%" height="200"/></div>
</div>
</div></div>
</section>
</div>
</t>"""

LOGGER = "odoo.addons.partner_microsite_manager.models.res_company"


class TestLegacyHomepageLiveData(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {
                "name": "Live Shop",
                "street": "Calle Nueva 5",
                "zip": "35010",
                "city": "Las Palmas",
                "phone": "928 11 11 11",
                "email": "shop@example.com",
                "microsite_parking_info": "Free car park behind the shop",
                "microsite_delivery_info": "Home delivery in the zone",
            }
        )
        cls.website = cls.env["website"].create(
            {"name": "Live Shop", "company_id": cls.company.id}
        )

    # -- helpers ---------------------------------------------------------
    def _legacy_page(self, arch_template=STANDARD_ARCH, slug="liveshop", website=None):
        website = website or self.website
        view = self.env["ir.ui.view"].create(
            {
                "name": f"Home - {slug}",
                "type": "qweb",
                "key": f"website.homepage_{slug}",
                "arch_db": arch_template.format(slug=slug),
                "website_id": website.id,
            }
        )
        self.env["website.page"].create(
            {
                "name": f"Home - {slug}",
                "url": "/",
                "view_id": view.id,
                "website_id": website.id,
                "is_published": True,
            }
        )
        return view

    def _render(self, view, website=None, **values):
        values["website"] = website or self.website
        return str(self.env["ir.qweb"]._render(view.id, values))

    def _relink(self, view):
        return self.env["res.company"]._relink_legacy_homepage_live_data(views=view)

    def _slots(self, *slots):
        self.env["microsite.opening.slot"].create(
            [
                {
                    "company_id": self.company.id,
                    "weekday": str(day),
                    "open_time": start,
                    "close_time": end,
                }
                for day, start, end in slots
            ]
        )

    # -- behaviour -------------------------------------------------------
    def test_the_relinked_page_shows_the_company_values(self):
        view = self._legacy_page()

        [stat] = self._relink(view)

        self.assertTrue(stat["written"])
        page = self._render(view)
        for current in (
            "928 11 11 11",
            'href="tel:928111111"',
            "Calle Nueva 5, 35010 Las Palmas",
            "mailto:shop@example.com",
            "Free car park behind the shop",
            "Home delivery in the zone",
            "output=embed",
        ):
            self.assertIn(current, page)
        for stale in (
            "928 00 00 00",
            "Old Town",
            "old @ example.com",
            "Parking nearby",
            "Delivery available",
            "q=Old+Street",
        ):
            self.assertNotIn(stale, page)
        # The design and the labels are the page's own, untouched.
        for kept in ("FIND US.", "Delivery / Shipping", "Our story", 'height="200"'):
            self.assertIn(kept, page)
        # Merchants cannot type into a live value in the builder.
        self.assertIn('data-cc-live="phone"', page)
        self.assertIn("o_not_editable", page)

    def test_editing_the_company_changes_the_page_not_the_view(self):
        view = self._legacy_page()
        self._relink(view)
        arch = view.arch_db

        self.company.write(
            {
                "microsite_phone": "690 11 62 79",
                "microsite_parking_info": "Blue zone",
            }
        )
        self.company.partner_id.write(
            {"email": "new@example.com", "street": "Calle Otra 9"}
        )

        page = self._render(view)
        self.assertIn("690 11 62 79", page)
        self.assertNotIn("928 11 11 11", page)
        self.assertIn("Blue zone", page)
        self.assertIn("new@example.com", page)
        self.assertIn("Calle Otra 9", page)
        self.assertEqual(view.arch_db, arch)

    def test_an_emptied_delivery_takes_its_card_with_it(self):
        view = self._legacy_page()
        self._relink(view)

        self.company.microsite_delivery_info = False

        page = self._render(view)
        self.assertNotIn("Delivery / Shipping", page)
        self.assertNotIn("fa-truck", page)
        self.assertIn("Parking", page)
        # The label is still in the arch, translations and all, for the day
        # the merchant fills the field again.
        self.assertIn("Delivery / Shipping", view.arch_db)
        self.company.microsite_delivery_info = "Back again"
        self.assertIn("Back again", self._render(view))

    def test_a_second_relink_writes_nothing(self):
        view = self._legacy_page()
        self._relink(view)
        arch = view.arch_db
        write_date = view.write_date

        [stat] = self._relink(view)

        self.assertFalse(stat["written"])
        self.assertEqual(view.arch_db, arch)
        self.assertEqual(view.write_date, write_date)

    def test_a_page_without_hours_gets_the_card_when_the_shop_has_hours(self):
        self._slots((0, 9.0, 14.0))
        view = self._legacy_page(CUSTOM_ARCH, slug="customshop")

        [stat] = self._relink(view)

        self.assertIn("hours", stat["inserted"])
        # A missing phone line is added next to its siblings.
        self.assertIn("phone", stat["inserted"])
        tree = etree.fromstring(view.arch_db.encode())
        sections = [s.get("data-name") for s in tree.iter("section")]
        self.assertLess(sections.index("Horario"), sections.index("Acerca"))
        page = self._render(view)
        self.assertIn("09:00 - 14:00", page)
        self.assertIn("Opening Hours", page)
        self.assertIn("928 11 11 11", page)
        # The importer's literal &nbsp; is gone with the static address.
        self.assertNotIn("nbsp", page)
        self.assertIn("Calle Nueva 5, 35010 Las Palmas", page)
        self.assertFalse(self._relink(view)[0]["written"])

    def test_a_page_without_a_contact_block_is_skipped_and_logged(self):
        view = self._legacy_page(
            '<t t-name="website.homepage_{slug}"><div id="wrap"><p>Hi</p></div></t>',
            slug="bare",
        )
        arch = view.arch_db

        # logging.INFO, not "INFO": Odoo maps that name to its level 25.
        with self.assertLogs(LOGGER, logging.INFO) as logs:
            [stat] = self._relink(view)

        self.assertTrue(stat["skipped"])
        self.assertFalse(stat["written"])
        self.assertEqual(view.arch_db, arch)
        self.assertIn(str(view.id), "\n".join(logs.output))

    def test_the_other_languages_keep_their_texts(self):
        self.env["res.lang"]._activate_lang("es_ES")
        view = self._legacy_page()
        view.update_field_translations(
            "arch_db",
            {
                "es_ES": {
                    "Parking": "Aparcamiento",
                    "Our story": "Nuestra historia",
                    "Delivery available": "Entrega disponible",
                }
            },
        )

        self._relink(view)

        spanish = view.with_context(lang="es_ES").arch_db
        self.assertIn("Aparcamiento", spanish)
        self.assertIn("Nuestra historia", spanish)
        self.assertNotIn("Entrega disponible", spanish)
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["delivery"], spanish)

    def test_a_builder_save_is_relinked_again(self):
        """The builder writes the rendered html back into the arch; the
        guard puts the t-calls back so the page keeps following the shop."""
        view = self._legacy_page()
        self._relink(view)
        # Rendered the way the builder renders it: ``editable``, so a card
        # without a value (no hours here) is still on the page to be saved.
        rendered = html.fromstring(self._render(view, editable=True))
        wrap = rendered.xpath("//div[@id='wrap']")[0]

        view.with_context(website_id=self.website.id).save(
            etree.tostring(wrap, encoding="unicode", method="html"),
            xpath="/t/div",
        )

        arch = view.arch_db
        self.assertNotIn("928 11 11 11", arch)
        self.assertNotIn("Free car park behind the shop", arch)
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["phone"], arch)
        self.assertIn(legacy_homepage.OPENING_HOURS_CARD_TEMPLATE, arch)
        self.assertIn("_get_microsite_map_url", arch)
        self.company.microsite_phone = "690 11 62 79"
        self.assertIn("690 11 62 79", self._render(view))

    def test_non_legacy_homepages_are_left_alone(self):
        other = self.env["res.company"].create({"name": "Dynamic Shop"})
        other_site = self.env["website"].create(
            {"name": "Dynamic", "company_id": other.id}
        )
        untouched = self.env["ir.ui.view"]
        for key in (
            "partner_microsite_manager.microsite_homepage_dyn",
            "theme_corporate_multi.corporate_homepage",
        ):
            view = self.env["ir.ui.view"].create(
                {
                    "name": key,
                    "type": "qweb",
                    "key": key,
                    "arch_db": STANDARD_ARCH.format(slug="dyn").replace(
                        "website.homepage_dyn", key
                    ),
                    "website_id": other_site.id,
                }
            )
            self.env["website.page"].create(
                {
                    "name": key,
                    "url": "/",
                    "view_id": view.id,
                    "website_id": other_site.id,
                }
            )
            untouched |= view
        archs = untouched.mapped("arch_db")
        legacy = self._legacy_page()

        stats = self.env["res.company"]._relink_legacy_homepage_live_data()

        self.assertIn(legacy.id, [s["view_id"] for s in stats])
        self.assertFalse({s["view_id"] for s in stats} & set(untouched.ids))
        self.assertEqual(untouched.mapped("arch_db"), archs)

    def test_zone_homepages_are_left_alone(self):
        if "zone_company_key" not in self.env["res.company"]._fields:
            self.skipTest("zone_company_ownership is not installed")
        zone = self.env["res.company"].create(
            {"name": "Zone", "zone_company_key": "guanarteme"}
        )
        zone_site = self.env["website"].create({"name": "Zone", "company_id": zone.id})
        view = self._legacy_page(slug="zone", website=zone_site)
        arch = view.arch_db

        stats = self.env["res.company"]._relink_legacy_homepage_live_data()

        self.assertNotIn(view.id, [s["view_id"] for s in stats])
        self.assertEqual(view.arch_db, arch)

    def test_contact_changes_empty_the_page_cache(self):
        registry = self.env.registry
        with patch.object(type(registry), "clear_cache") as clear_cache:
            self.company.partner_id.write({"phone": "928 22 22 22"})
            clear_cache.assert_called_with("templates")
            clear_cache.reset_mock()
            self.env["res.partner"].create({"name": "Somebody"}).write(
                {"phone": "600 00 00 00"}
            )
            clear_cache.assert_not_called()
            self.company.write({"microsite_delivery_info": "Changed"})
            clear_cache.assert_called_with("templates")

    def test_the_address_is_decoded(self):
        self.company.partner_id.write(
            {"street": "Calle Vieja 23&nbsp;35010", "street2": False}
        )
        self.assertEqual(
            self.company._get_microsite_live_address(),
            "Calle Vieja 23, 35010 Las Palmas",
        )

    def test_the_post_migration_backs_up_and_relinks(self):
        view = self._legacy_page()
        original = view.arch_db
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations",
            "19.0.2.13.0",
            "post-migration.py",
        )
        spec = importlib.util.spec_from_file_location("pmm_post_migration_2130", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # A fresh install has no version and nothing to migrate.
        module.migrate(self.env.cr, None)
        view.invalidate_recordset()
        self.assertEqual(view.arch_db, original)

        module.migrate(self.env.cr, "19.0.2.12.0")

        view.invalidate_recordset()
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["phone"], view.arch_db)
        Attachment = self.env["ir.attachment"]
        domain = [
            ("res_model", "=", "ir.ui.view"),
            ("res_id", "=", view.id),
            ("name", "=", f"legacy-homepage-backup-{view.id}-19.0.2.13.0.json"),
        ]
        backup = Attachment.search(domain)
        self.assertEqual(len(backup), 1)
        self.assertEqual(json.loads(backup.raw)["en_US"], original)
        # A second run keeps the first backup and writes nothing.
        module.migrate(self.env.cr, "19.0.2.12.0")
        self.assertEqual(Attachment.search_count(domain), 1)
