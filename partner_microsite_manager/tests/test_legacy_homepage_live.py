# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import csv
import importlib.util
import io
import json
import logging
import os
from unittest.mock import patch

from lxml import etree, html

from odoo.exceptions import ConcurrencyError
from odoo.tests.common import TransactionCase, new_test_user

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
<p class="mb-2"><i class="fa fa-map-marker fa-fw mr-2 text-primary"/>Calle Nueva, 5 - Las Palmas</p>
<p class="mb-2"><i class="fa fa-phone fa-fw mr-2 text-primary"/>928 00 00 00</p>
<p class="mb-2"><i class="fa fa-envelope fa-fw mr-2 text-primary"/>Shop @ example.com</p>
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

    def _relink(self, view, mode="migration", kinds=()):
        if mode == "migration":
            # As the migration does: back the page up first (later relinks
            # only touch pages that have their 19.0.2.13.0 backup).
            self._backup(view)
        return self.env["res.company"]._relink_legacy_homepage_live_data(
            views=view, mode=mode, kinds=kinds
        )

    def _backup(self, views):
        for view in views:
            self._migration_module()._backup_arch(self.env, view.id)

    def _patch_relinker(self):
        """Make the relinker itself fail, so the OUTER handlers are tested."""
        return patch.object(
            type(self.env["res.company"]),
            "_relink_legacy_homepage_live_data",
            side_effect=RuntimeError("boom"),
        )

    def _builder_save(self, view, drop_xpath=None):
        """Save ``view`` the way the website builder does: the html rendered
        in edit mode goes back into the arch (``ir.ui.view.save``)."""
        rendered = html.fromstring(self._render(view, editable=True))
        wrap = rendered.xpath("//div[@id='wrap']")[0]
        for element in wrap.xpath(drop_xpath) if drop_xpath else []:
            element.getparent().remove(element)
        view.with_context(website_id=self.website.id).save(
            etree.tostring(wrap, encoding="unicode", method="html"),
            xpath="/t/div",
        )

    def _migration_module(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations",
            "19.0.2.13.0",
            "post-migration.py",
        )
        spec = importlib.util.spec_from_file_location("pmm_post_migration_2130", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

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
            "Calle Nueva, 5 - Las Palmas",
            "Shop @ example.com",
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

        self.assertEqual(stat["inserted"], ["hours"])
        tree = etree.fromstring(view.arch_db.encode())
        sections = [s.get("data-name") for s in tree.iter("section")]
        self.assertLess(sections.index("Horario"), sections.index("Acerca"))
        page = self._render(view)
        self.assertIn("09:00 - 14:00", page)
        self.assertIn("Opening Hours", page)
        # Contact lines are never added: the page had no phone line.
        self.assertNotIn("928 11 11 11", page)
        # A different address (shop vs. fiscal) is kept as the page shows it.
        self.assertEqual(
            [(k["kind"], k["reason"]) for k in stat["kept_static"]],
            [
                ("address", "differs"),
                ("email", "differs"),
                ("map", "no_map_url_and_address_static"),
            ],
        )
        self.assertIn("Calle Vieja 23", page)
        self.assertIn("q=Calle+Vieja", page)
        self.assertFalse(self._relink(view)[0]["written"])

    def test_only_the_migration_adds_what_the_page_lacks(self):
        self._slots((0, 9.0, 14.0))
        view = self._legacy_page(CUSTOM_ARCH, slug="noinsert")

        self._backup(view)
        [stat] = self._relink(view, mode="guard")

        self.assertFalse(stat["inserted"])
        self.assertNotIn('data-name="Horario"', view.arch_db)
        # A builder save never turns a static line live.
        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["email"], view.arch_db)
        self.assertIn("old@example.com", view.arch_db)

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
        self._builder_save(view)

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

    def test_a_line_deleted_in_the_builder_stays_deleted(self):
        view = self._legacy_page()
        self._relink(view)

        self._builder_save(view, drop_xpath="//p[.//*[@data-cc-live='email']]")

        arch = view.arch_db
        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["email"], arch)
        self.assertNotIn("shop@example.com", arch)
        # The other, flattened lines are live again.
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["phone"], arch)
        self.assertNotIn("928 11 11 11", arch)
        self.assertNotIn("shop@example.com", self._render(view))

    def test_a_failing_relink_never_breaks_a_save(self):
        view = self._legacy_page()
        self._backup(view)
        new_arch = view.arch_db.replace("Our story", "Our new story")
        with (
            self._patch_relinker(),
            self.assertLogs(
                "odoo.addons.partner_microsite_manager.models.ir_ui_view",
                logging.WARNING,
            ) as logs,
        ):
            view.write({"arch": new_arch})

        self.assertIn("Our new story", view.arch_db)
        self.assertIn("928 00 00 00", view.arch_db)
        self.assertIn(str(view.id), "\n".join(logs.output))

    def test_the_page_cache_is_emptied_only_by_a_change(self):
        registry = self.env.registry
        partner = self.company.partner_id
        postcommit = self.env.cr.postcommit
        postcommit.run()  # whatever the fixtures queued
        with patch.object(type(registry), "clear_cache") as clear_cache:
            partner.write({"phone": "928 22 22 22"})
            partner.write({"email": "other@example.com"})
            clear_cache.assert_not_called()  # at commit, not before
            postcommit.run()
            clear_cache.assert_called_once_with("templates")  # once per transaction
            clear_cache.reset_mock()
            partner.write({"phone": "928 22 22 22"})
            partner.write({"comment": "unrelated"})
            self.env["res.partner"].create({"name": "Somebody"}).write(
                {"phone": "600 00 00 00"}
            )
            self.company.write({"microsite_delivery_info": "Home delivery in the zone"})
            postcommit.run()
            clear_cache.assert_not_called()
            self.company.write({"microsite_delivery_info": "Changed"})
            postcommit.run()
            clear_cache.assert_called_once_with("templates")
            clear_cache.reset_mock()
            # The hours text is a stored compute: the rows clear it too.
            self._slots((2, 9.0, 13.0))
            postcommit.run()
            clear_cache.assert_called_once_with("templates")

    def test_only_http_links_reach_the_page(self):
        partner = self.company.partner_id
        for value in (
            "javascript://x%0aalert(1)",
            "JaVaScRiPt:alert(1)",
            "java\tscript:alert(1)",
            "data:text/html;base64,PHNjcmlwdD4=",
        ):
            partner.website = value
            self.assertEqual(self.company._get_microsite_website_url(), "", value)
            self.assertFalse(self.company._microsite_live_has("website"))
        # Core stores a bare host as ``http://...``; the helper keeps it.
        for value in (
            "//shop.example.com",
            "shop.example.com",
            "https://shop.example.com/a",
        ):
            partner.website = value
            url = self.company._get_microsite_website_url()
            self.assertRegex(url, r"^https?://shop\.example\.com(/a)?$", value)
        self.website.social_facebook = "javascript:alert(1)"
        self.website.social_instagram = "https://www.instagram.com/shop"
        hrefs = [link["href"] for link in self.website._pmm_footer_social_links()]
        self.assertEqual(hrefs, ["https://www.instagram.com/shop"])
        partner.website = "javascript:alert(1)"
        view = self._legacy_page(
            STANDARD_ARCH.replace(
                '<p class="mb-2"><i class="fa fa-envelope',
                '<p class="mb-2"><i class="fa fa-globe fa-fw"/>old.example</p>'
                '<p class="mb-2"><i class="fa fa-envelope',
            )
        )
        self._relink(view)
        self.assertNotIn("javascript", self._render(view).lower())

    def test_the_backup_restores_every_language(self):
        self.env["res.lang"]._activate_lang("es_ES")
        view = self._legacy_page()
        # Without the guard: the page must reach the migration static.
        view.with_context(pmm_live_relink=True).update_field_translations(
            "arch_db", {"es_ES": {"Delivery available": "Entrega disponible"}}
        )
        original_en = view.with_context(lang="en_US").arch_db
        original_es = view.with_context(lang="es_ES").arch_db
        module = self._migration_module()
        module.migrate(self.env.cr, "19.0.2.12.0")
        view.invalidate_recordset()
        self.assertNotIn("Entrega disponible", view.with_context(lang="es_ES").arch_db)

        restored = self.env["res.company"]._restore_legacy_homepage_backup(view)

        self.assertEqual(restored, view)
        self.assertEqual(view.with_context(lang="en_US").arch_db, original_en)
        self.assertEqual(view.with_context(lang="es_ES").arch_db, original_es)
        self.assertIn("928 00 00 00", self._render(view))

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
        module = self._migration_module()

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

    # -- what each page shows is preserved; a human edit wins ----------------
    def _mismatching_page(self, slug="mismatch"):
        return self._legacy_page(
            STANDARD_ARCH.replace("Shop @ example.com", "public@example.com").replace(
                "Calle Nueva, 5 - Las Palmas",
                "Paseo Tomas Morales 72, Las Palmas 35003",
            ),
            slug=slug,
        )

    def test_a_page_showing_other_contact_data_keeps_it(self):
        view = self._mismatching_page()

        [stat] = self._relink(view)

        kept = {k["kind"]: k for k in stat["kept_static"]}
        self.assertEqual(set(kept), {"email", "address", "map"})
        self.assertEqual(kept["email"]["shown"], "public@example.com")
        self.assertEqual(kept["email"]["live"], "shop@example.com")
        page = self._render(view)
        self.assertIn("public@example.com", page)
        self.assertIn("Paseo Tomas Morales 72", page)
        self.assertIn("q=Old+Street", page)
        self.assertNotIn("shop@example.com", page)
        # Phone, parking, delivery and hours follow the company regardless.
        self.assertIn("928 11 11 11", page)
        # A builder save does not change that either.
        self._builder_save(view)
        self.assertIn("public@example.com", self._render(view))

    def test_a_human_edit_makes_the_value_live(self):
        view = self._mismatching_page(slug="humanedit")
        self._relink(view)

        self.company.partner_id.write({"email": "new@example.com"})

        page = self._render(view)
        self.assertIn("new@example.com", page)
        self.assertNotIn("public@example.com", page)
        self.assertIn("Paseo Tomas Morales 72", page)  # not edited: kept

        self.company.partner_id.write({"street": "Calle Otra 9"})

        page = self._render(view)
        self.assertIn("Calle Otra 9, 35010 Las Palmas", page)
        self.assertNotIn("Paseo Tomas Morales", page)
        # The map follows the address it now shows.
        self.assertNotIn("q=Old+Street", page)
        self.assertIn("Calle+Otra", page)

    def test_an_emptied_value_is_not_forced(self):
        view = self._mismatching_page(slug="emptied")
        self._relink(view)

        self.company.partner_id.write({"email": False})

        self.assertIn("public@example.com", self._render(view))

    def test_a_new_map_link_makes_the_map_live(self):
        view = self._mismatching_page(slug="maplink")
        self._relink(view)

        self.company.write(
            {
                "microsite_map_url": "https://maps.google.com/maps?q=New+Place&output=embed"
            }
        )

        page = self._render(view)
        self.assertIn("q=New+Place", page)
        self.assertNotIn("q=Old+Street", page)

    def test_bulk_writes_do_not_rewrite_pages(self):
        view = self._mismatching_page(slug="bulk")
        self._relink(view)
        arch = view.arch_db
        for key in ("install_mode", "module", "import_file"):
            self.company.partner_id.with_context(**{key: True}).write(
                {"email": f"{key}@example.com"}
            )
            self.assertEqual(view.arch_db, arch, key)

    def test_a_failing_edit_relink_never_breaks_the_write(self):
        view = self._mismatching_page(slug="editfail")
        self._relink(view)
        with self._patch_relinker(), self.assertLogs(LOGGER, logging.WARNING):
            self.company.partner_id.write({"email": "new@example.com"})
        self.assertEqual(self.company.partner_id.email, "new@example.com")

    def test_a_failing_page_does_not_stop_the_migration(self):
        first = self._legacy_page(slug="first")
        second = self._legacy_page(slug="second")
        real = legacy_homepage.relink_live_data

        def flaky(arch, *args, **kwargs):
            if "homepage_first" in arch:
                raise RuntimeError("boom")
            return real(arch, *args, **kwargs)

        target = (
            "odoo.addons.partner_microsite_manager.models.res_company."
            "legacy_homepage.relink_live_data"
        )
        with patch(target, side_effect=flaky), self.assertLogs(LOGGER, logging.ERROR):
            stats = self.env["res.company"]._relink_legacy_homepage_live_data(
                views=first | second
            )
        by_view = {s["view_id"]: s for s in stats}
        self.assertTrue(by_view[first.id]["failed"])
        self.assertTrue(by_view[second.id]["written"])
        self.assertIn("928 00 00 00", first.arch_db)

    # -- translations safety net ----------------------------------------------
    def _raw(self, view):
        return self.env["res.company"]._get_arch_db_raw(view)

    def test_a_language_copy_out_of_step_is_left_alone(self):
        self.env["res.lang"]._activate_lang("es_ES")
        view = self._legacy_page(slug="outofstep")
        raw = self._raw(view)
        # A Spanish copy with one paragraph more than the source: its terms
        # no longer line up, and a lang=None write would turn it English.
        spanish = raw["en_US"].replace(
            "<p>Our story</p>", "<p>Nuestra historia</p><p>Solo en castellano</p>"
        )
        self.env.cr.execute(
            "UPDATE ir_ui_view SET arch_db = arch_db || jsonb_build_object('es_ES', %s::text)"
            " WHERE id = %s",
            [spanish, view.id],
        )
        view.invalidate_recordset()
        before = self._raw(view)

        with self.assertLogs(LOGGER, logging.WARNING):
            [stat] = self._relink(view)

        self.assertEqual(stat["skipped"], "translation structure mismatch")
        self.assertFalse(stat["written"])
        self.assertEqual(self._raw(view), before)

    def test_a_language_copy_in_step_keeps_every_other_text(self):
        self.env["res.lang"]._activate_lang("es_ES")
        view = self._legacy_page(slug="instep")
        field = view._fields["arch_db"]
        view.with_context(pmm_live_relink=True).update_field_translations(
            "arch_db",
            {
                "es_ES": {
                    "Parking": "Aparcamiento",
                    "Our story": "Nuestra historia",
                    "Delivery available": "Entrega disponible",
                    "FIND US.": "ENCUENTRANOS.",
                }
            },
        )
        before = self._raw(view)

        [stat] = self._relink(view)

        self.assertTrue(stat["written"])
        after = self._raw(view)
        removed = set(field.get_trans_terms(before["en_US"])) - set(
            field.get_trans_terms(after["en_US"])
        )
        dictionary = field.get_translation_dictionary(
            before["en_US"], {"es_ES": before["es_ES"]}
        )
        expected = set(field.get_trans_terms(before["es_ES"])) - {
            dictionary[term]["es_ES"] for term in removed
        }
        self.assertEqual(set(field.get_trans_terms(after["es_ES"])), expected)
        self.assertIn("Entrega disponible", before["es_ES"])
        self.assertNotIn("Entrega disponible", after["es_ES"])

    # -- assumptions and earlier paths ----------------------------------------
    def test_a_generic_view_is_never_a_target(self):
        """All 207 legacy views are website-specific on prod; a generic one
        (shared, edited through copy-on-write) is never relinked."""
        view = self._legacy_page(slug="generic")
        # Straight in the column: the ORM would copy-on-write instead.
        self.env.cr.execute(
            "UPDATE ir_ui_view SET website_id = NULL WHERE id = %s", [view.id]
        )
        view.invalidate_recordset()
        self.assertFalse(
            self.env["res.company"]._get_legacy_homepage_views(view_ids=view.ids)
        )

    def test_the_hours_relink_of_2_8_0_does_not_relink_the_rest(self):
        view = self._legacy_page(
            STANDARD_ARCH.replace(
                '<t t-call="partner_microsite_manager.microsite_opening_hours_card"/>',
                '<div class="horario-card-accordion"><span>Lunes</span></div>',
            ),
            slug="old280",
        )

        self.company._relink_legacy_opening_hours_card()

        self.assertIn(legacy_homepage.OPENING_HOURS_CARD_TEMPLATE, view.arch_db)
        # Still static: 19.0.2.13.0 backs the page up before relinking it.
        self.assertIn("928 00 00 00", view.arch_db)

    def test_the_migration_lists_what_it_kept_for_review(self):
        view = self._mismatching_page(slug="review")
        module = self._migration_module()

        module.migrate(self.env.cr, "19.0.2.12.0")

        review = self.env["ir.attachment"].search(
            [("name", "=", "legacy-homepage-review-19.0.2.13.0.csv")]
        )
        self.assertEqual(len(review), 1)
        self.assertFalse(review.public)
        rows = list(csv.DictReader(io.StringIO(review.raw.decode())))
        mine = {r["kind"]: r for r in rows if r["company_id"] == str(self.company.id)}
        self.assertEqual(set(mine), {"email", "address", "map"})
        self.assertEqual(mine["email"]["shown_on_page"], "public@example.com")
        self.assertEqual(mine["email"]["contact_value"], "shop@example.com")
        self.assertEqual(mine["email"]["reason"], "differs")
        self.assertIn("public@example.com", self._render(view))
        # Rewritten, not duplicated, on a second run.
        module.migrate(self.env.cr, "19.0.2.12.0")
        self.assertEqual(
            self.env["ir.attachment"].search_count(
                [("name", "=", "legacy-homepage-review-19.0.2.13.0.csv")]
            ),
            1,
        )

    # -- decisions taken on the copy the page was written in ------------------
    def _two_language_page(self, slug, english, spanish):
        """A page whose en_US copy shows ``english`` (email, address) and
        whose es_ES copy -- the website's language -- shows ``spanish``."""
        es = self.env["res.lang"]._activate_lang("es_ES")
        self.website.language_ids |= es
        self.website.default_lang_id = es
        view = self._legacy_page(
            STANDARD_ARCH.replace("Shop @ example.com", english[0]).replace(
                "Calle Nueva, 5 - Las Palmas", english[1]
            ),
            slug=slug,
        )
        raw = self._raw(view)
        spanish_arch = (
            raw["en_US"].replace(english[0], spanish[0]).replace(english[1], spanish[1])
        )
        self.env.cr.execute(
            "UPDATE ir_ui_view SET arch_db = arch_db || jsonb_build_object('es_ES', %s::text)"
            " WHERE id = %s",
            [spanish_arch, view.id],
        )
        view.invalidate_recordset()
        return view

    def test_the_authoring_copy_decides_not_the_machine_translation(self):
        view = self._two_language_page(
            "authoring",
            english=("shopconditioning", "New Street 5, The Palms"),
            spanish=("Shop @ example.com", "Calle Nueva, 5 - Las Palmas"),
        )

        [stat] = self._relink(view)

        self.assertTrue(stat["written"])
        self.assertFalse(stat["kept_static"])
        for lang in ("en_US", "es_ES"):
            arch = self._raw(view)[lang]
            self.assertIn(legacy_homepage.LIVE_TEMPLATES["email"], arch, lang)
            self.assertIn(legacy_homepage.LIVE_TEMPLATES["address"], arch, lang)
            self.assertNotIn("shopconditioning", arch, lang)

    def test_a_differing_authoring_copy_keeps_the_values(self):
        view = self._two_language_page(
            "authoringdiff",
            english=("Shop @ example.com", "Calle Nueva, 5 - Las Palmas"),
            spanish=("tienda@example.com", "Paseo Tomas Morales 72, Las Palmas 35003"),
        )

        [stat] = self._relink(view)

        kept = {k["kind"]: k for k in stat["kept_static"]}
        self.assertEqual(set(kept), {"email", "address", "map"})
        # The review list shows what the Spanish page shows.
        self.assertEqual(kept["email"]["shown"], "tienda@example.com")
        arch = self._raw(view)["es_ES"]
        self.assertIn("tienda@example.com", arch)
        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["email"], arch)
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["phone"], arch)

    # -- final review ----------------------------------------------------------
    def _as_user(self, record, user):
        """Make ``record`` look created by ``user`` (as if they had)."""
        self.env.cr.execute(
            f"UPDATE {record._table} SET create_uid = %s WHERE id = %s",
            [user.id, record.id],
        )
        record.invalidate_recordset()

    def test_only_an_explicit_map_link_makes_the_map_live(self):
        view = self._mismatching_page(slug="maponlyexplicit")
        self._relink(view)
        self.assertIn("q=Old+Street", self._render(view))

        # The cron converting stored links is not a person choosing a map.
        self.company.with_context(pmm_map_normalize=True).write(
            {"microsite_map_url": "https://maps.google.com/maps?q=Cron&output=embed"}
        )
        self.assertIn("q=Old+Street", self._render(view))
        # Clearing the link never swaps in the partner-address map.
        self.company.write({"microsite_map_url": False})
        self.assertIn("q=Old+Street", self._render(view))

        self.company.write(
            {
                "microsite_map_url": "https://maps.google.com/maps?q=New+Place&output=embed"
            }
        )
        page = self._render(view)
        self.assertIn("q=New+Place", page)
        self.assertNotIn("q=Old+Street", page)

    def test_only_the_migration_backup_is_trusted(self):
        view = self._legacy_page(slug="trusted")
        original = self._raw(view)
        self._migration_module().migrate(self.env.cr, "19.0.2.12.0")
        user = new_test_user(self.env, login="pmm_backup_user")
        name = f"legacy-homepage-backup-{view.id}-19.0.2.13.0.json"
        forged = self.env["ir.attachment"].create(
            {
                "name": name,
                "raw": json.dumps({"en_US": "<t t-name='x'>forged</t>"}).encode(),
                "res_model": "ir.ui.view",
                "res_id": view.id,
            }
        )
        self._as_user(forged, user)

        self.env["res.company"]._restore_legacy_homepage_backup(view)

        self.assertEqual(self._raw(view), original)
        # A second migration run does not take the forged one for its own
        # either (the original backup is still there and still first).
        self.assertEqual(
            self.env["res.company"]._find_legacy_homepage_backup(view.id).create_uid.id,
            self.env.ref("base.user_root").id,
        )

    def test_a_malformed_backup_is_not_restored(self):
        Company = self.env["res.company"]
        self.assertFalse(Company._is_valid_arch_backup(["<t/>"]))
        self.assertFalse(Company._is_valid_arch_backup({"es_ES": "<t/>"}))
        self.assertFalse(
            Company._is_valid_arch_backup({"en_US": "<t/>", "x y": "<t/>"})
        )
        self.assertFalse(Company._is_valid_arch_backup({"en_US": 3}))
        self.assertTrue(
            Company._is_valid_arch_backup({"en_US": "<t/>", "es_ES": "<t/>"})
        )

    def test_the_review_list_is_for_administrators_only(self):
        self._mismatching_page(slug="reviewaccess")
        user = new_test_user(self.env, login="pmm_review_user")
        planted = self.env["ir.attachment"].create(
            {"name": "legacy-homepage-review-19.0.2.13.0.csv", "raw": b"planted"}
        )
        self._as_user(planted, user)

        self._migration_module().migrate(self.env.cr, "19.0.2.12.0")

        review = self.env["ir.attachment"].search(
            [
                ("name", "=", "legacy-homepage-review-19.0.2.13.0.csv"),
                ("create_uid", "=", self.env.ref("base.user_root").id),
            ]
        )
        self.assertEqual(len(review), 1)
        self.assertFalse(review.res_model)
        self.assertFalse(review.res_id)
        self.assertFalse(review.public)
        self.assertIn("public@example.com", review.raw.decode())
        self.assertEqual(planted.raw, b"planted")

    # -- final reliability batch -------------------------------------------------
    def test_nothing_but_the_migration_touches_a_page_not_backed_up(self):
        view = self._mismatching_page(slug="nobackup")
        arch = view.arch_db

        self.company.partner_id.write({"email": "new@example.com"})
        view.write({"arch": arch.replace("Our story", "Our new story")})

        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["email"], view.arch_db)
        self.assertIn("928 00 00 00", view.arch_db)
        self.assertIn("Our new story", view.arch_db)
        # Once backed up, a person's edit goes live as usual.
        self._backup(view)
        self.company.partner_id.write({"email": "newer@example.com"})
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["email"], view.arch_db)

    def test_a_normalised_web_address_is_no_human_edit(self):
        partner = self.company.partner_id
        partner.website = "www.shop.com"
        view = self._legacy_page(
            STANDARD_ARCH.replace(
                '<p class="mb-2"><i class="fa fa-envelope',
                '<p class="mb-2"><i class="fa fa-globe fa-fw"/>old.example</p>'
                '<p class="mb-2"><i class="fa fa-envelope',
            ),
            slug="webnorm",
        )
        self._relink(view)
        arch = view.arch_db
        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["website"], arch)

        partner.website = "https://www.shop.com/"

        self.assertEqual(view.arch_db, arch)
        partner.website = "https://other.example"
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["website"], view.arch_db)

    def test_a_multi_partner_write_relinks_only_what_changed(self):
        other = self.env["res.company"].create(
            {
                "name": "Other Shop",
                "street": "Calle Nueva 5",
                "zip": "35010",
                "city": "Las Palmas",
                "email": "x@example.com",
            }
        )
        other_site = self.env["website"].create(
            {"name": "Other", "company_id": other.id}
        )
        mine = self._mismatching_page(slug="multimine")
        theirs = self._legacy_page(
            STANDARD_ARCH.replace("Shop @ example.com", "public@example.com"),
            slug="multitheirs",
            website=other_site,
        )
        self._relink(mine | theirs)
        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["email"], theirs.arch_db)

        (self.company.partner_id | other.partner_id).write({"email": "x@example.com"})

        self.assertIn(legacy_homepage.LIVE_TEMPLATES["email"], mine.arch_db)
        # The other shop already had that email: nothing changed for it.
        self.assertNotIn(legacy_homepage.LIVE_TEMPLATES["email"], theirs.arch_db)
        self.assertIn("public@example.com", theirs.arch_db)

    def test_retryable_errors_are_not_swallowed(self):
        view = self._mismatching_page(slug="retry")
        self._relink(view)
        with (
            patch.object(
                type(self.env["res.company"]),
                "_relink_legacy_homepage_live_data",
                side_effect=ConcurrencyError("busy"),
            ),
            self.assertRaises(ConcurrencyError),
        ):
            self.company.partner_id.write({"email": "new@example.com"})

    def test_failed_and_mismatched_pages_are_in_the_review_list(self):
        view = self._legacy_page(slug="reviewfailed")
        module = self._migration_module()
        target = (
            "odoo.addons.partner_microsite_manager.models.res_company."
            "legacy_homepage.relink_live_data"
        )
        with (
            patch(target, side_effect=RuntimeError("boom")),
            self.assertLogs(LOGGER, logging.ERROR),
        ):
            module.migrate(self.env.cr, "19.0.2.12.0")
        review = self.env["ir.attachment"].search(
            [("name", "=", "legacy-homepage-review-19.0.2.13.0.csv")]
        )
        rows = list(csv.DictReader(io.StringIO(review.raw.decode())))
        self.assertIn(
            ("page", "failed"),
            [
                (r["kind"], r["reason"])
                for r in rows
                if r["company_id"] == str(self.company.id)
            ],
        )
        self.assertIn("928 00 00 00", view.arch_db)
