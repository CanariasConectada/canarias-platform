# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import new_test_user, tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCompanyFacilities(TransactionCase):
    """What a shop offers, grouped and in order, on its own microsite.

    Asked for on 2026-08-16: "lo vamos a llamar ahora Instalaciones y
    servicios […] con todo el tema de subdivisiones e iconos y demás que lo
    pueda definir el cliente y nosotros". Simplified on 2026-09-15: no
    switch, the ticks decide; the title says what it is; the list is in
    catalogue order under its subdivisions.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Comercio con extras"})
        cls.website = cls.env["website"].create(
            {"name": "Comercio con extras", "company_id": cls.company.id}
        )
        cls.company.website_id = cls.website
        cls.Category = cls.env["company.facility.category"]
        cls.Facility = cls.env["company.facility"]
        cls.Editor = cls.env["microsite.content.editor"]
        cls.access = cls.Category.create(
            {"name": "Acceso", "icon": "fa-universal-access", "sequence": 1}
        )
        cls.payment = cls.Category.create(
            {"name": "Pago", "icon": "fa-credit-card", "sequence": 2}
        )
        cls.ramp = cls.Facility.create(
            {"name": "Rampa", "category_id": cls.access.id, "sequence": 2}
        )
        cls.lift = cls.Facility.create(
            {"name": "Ascensor", "category_id": cls.access.id, "sequence": 1}
        )
        cls.card = cls.Facility.create(
            {"name": "Tarjeta", "category_id": cls.payment.id, "icon": "fa-credit-card"}
        )
        cls.bizum = cls.Facility.create(
            {"name": "Bizum", "category_id": cls.payment.id}
        )
        cls.merchant = new_test_user(
            cls.env,
            login="facilities_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.company.id,
            company_ids=[(6, 0, cls.company.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _render_block(self):
        return self.env["ir.qweb"]._render(
            "company_facilities.facilities_block", {"cf_company": self.company}
        )

    def _render_homepage(self):
        return self.env["ir.qweb"]._render(
            "partner_microsite_manager.microsite_homepage_content",
            {"website": self.website},
        )

    # ------------------------------------------------------------------
    # The catalogue
    # ------------------------------------------------------------------
    def test_the_starter_catalogue_is_there_to_pick_from(self):
        seeded = self.env.ref("company_facilities.facility_step_free_access")
        self.assertTrue(seeded.exists())
        self.assertEqual(
            seeded.category_id,
            self.env.ref("company_facilities.category_accessibility"),
        )

    def test_the_catalogue_is_ordered_by_subdivision_then_sequence_then_name(self):
        """The order the merchant sees is the order the catalogue defines.

        "Sin orden" was the complaint (2026-09-15): the many-to-many came
        back as tags in whatever order they were ticked. ``_order`` on the
        item follows the subdivision's own order first, so anything that
        reads the catalogue -- the checkboxes, the tags, the microsite --
        agrees on the same sequence without sorting by hand.
        """
        mine = self.ramp + self.lift + self.card + self.bizum
        found = self.Facility.search([("id", "in", mine.ids)])
        self.assertEqual(
            found.mapped("name"),
            ["Ascensor", "Rampa", "Bizum", "Tarjeta"],
            "subdivision sequence, then item sequence, then name",
        )
        # A many-to-many READ comes back in relation-table order, not in
        # ``_order`` (Odoo 19): anything that shows a shop's own selection
        # sorts it first, and ``sorted()`` with no key is the ``_order``.
        self.company.facility_ids = self.card + self.ramp + self.bizum + self.lift
        self.assertEqual(
            self.company.facility_ids.sorted().mapped("name"),
            ["Ascensor", "Rampa", "Bizum", "Tarjeta"],
            "the shop's own selection follows the catalogue once sorted",
        )

    def test_the_catalogue_opens_grouped_by_subdivision(self):
        action = self.env.ref("company_facilities.action_company_facility")
        self.assertEqual(action.context, "{'search_default_by_category': 1}")

    def test_the_same_item_cannot_be_created_twice_in_a_subdivision(self):
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.Facility.create({"name": "Rampa", "category_id": self.access.id})

    def test_a_subdivision_in_use_cannot_be_deleted_by_accident(self):
        with self.assertRaises(Exception):
            with self.env.cr.savepoint():
                self.access.unlink()

    def test_the_catalogue_is_in_the_automatic_translation_rollout(self):
        """A shop adding "Parking gratuito" must not need a developer.

        The whole point of the catalogue being editable by the client is that
        they will edit it, and every word of it is read by visitors in four
        languages.
        """
        self.assertIn("name", self.Facility._auto_translate_fields())
        self.assertIn("description", self.Facility._auto_translate_fields())
        self.assertIn("name", self.Category._auto_translate_fields())

    # ------------------------------------------------------------------
    # What a shop offers
    # ------------------------------------------------------------------
    def test_what_a_shop_offers_comes_out_grouped_and_in_order(self):
        self.company.facility_ids = self.ramp + self.card + self.lift
        grouped = self.company._facilities_by_category()
        self.assertEqual([category.name for category, _ in grouped], ["Acceso", "Pago"])
        self.assertEqual(
            [item.name for item in grouped[0][1]],
            ["Ascensor", "Rampa"],
            "the sequence of the catalogue is what orders the microsite",
        )

    def test_a_shop_offering_nothing_shows_no_block_at_all(self):
        self.company.facility_ids = [(5, 0, 0)]
        self.assertEqual(self.company._facilities_by_category(), [])

    def test_archiving_an_item_removes_it_from_every_microsite_at_once(self):
        self.company.facility_ids = self.ramp + self.lift
        self.lift.active = False
        offered = [
            item.name
            for _, items in self.company._facilities_by_category()
            for item in items
        ]
        self.assertEqual(offered, ["Rampa"])

    def test_an_empty_subdivision_does_not_leave_a_heading_behind(self):
        self.company.facility_ids = self.card
        grouped = self.company._facilities_by_category()
        self.assertEqual([category.name for category, _ in grouped], ["Pago"])

    # ------------------------------------------------------------------
    # The section on the microsite
    # ------------------------------------------------------------------
    def test_the_section_is_hidden_until_the_shop_ticks_something(self):
        """No switch: the ticks decide (2026-09-15).

        A switch next to an empty list was a way to show a heading over
        nothing, and a way to tick things and see nothing. Now the section
        renders exactly when there is something to render.
        """
        self.company.facility_ids = [(5, 0, 0)]
        self.assertNotIn("o_cf_facilities", self._render_homepage())
        self.company.facility_ids = self.ramp
        html = self._render_homepage()
        self.assertIn("o_cf_facilities", html)
        self.assertIn("Rampa", html)

    def test_the_section_lists_items_by_subdivision_then_sequence(self):
        self.company.facility_ids = self.card + self.ramp + self.bizum + self.lift
        html = self._render_block()
        positions = [
            html.index(name)
            for name in ("Acceso", "Ascensor", "Rampa", "Pago", "Bizum", "Tarjeta")
        ]
        self.assertEqual(
            positions, sorted(positions), "the page follows the catalogue order"
        )

    def test_the_block_renders_what_the_shop_ticked(self):
        self.company.facility_ids = self.ramp + self.card
        self.company.facility_block_title = "Instalaciones y servicios"
        rendered = self._render_block()
        self.assertIn("Instalaciones y servicios", rendered)
        self.assertIn("Rampa", rendered)
        self.assertIn("Tarjeta", rendered)
        self.assertIn("fa-credit-card", rendered)

    def test_the_block_falls_back_to_the_default_heading_when_the_title_is_empty(self):
        self.company.facility_ids = self.ramp
        self.company.facility_block_title = False
        self.assertIn("Facilities and services", self._render_block())
        self.company.facility_block_title = "Lo que encontrarás"
        rendered = self._render_block()
        self.assertIn("Lo que encontrarás", rendered)
        self.assertNotIn("Facilities and services", rendered)

    def test_the_block_no_longer_hangs_off_the_site_layout(self):
        """Above ``div#footer`` it rendered after the funding strip.

        The client wants a homepage to end contact, strip, footer
        (2026-09-16): the block now lives inside the homepage itself.
        """
        self.assertFalse(
            self.env.ref(
                "company_facilities.layout_facilities", raise_if_not_found=False
            )
        )

    # ------------------------------------------------------------------
    # The merchant's screen
    # ------------------------------------------------------------------
    def test_the_switch_is_gone_from_the_model_and_the_screens(self):
        self.assertNotIn("facility_block_enabled", self.env["res.company"]._fields)
        self.assertNotIn("facility_block_enabled", self.Editor._fields)
        editor_view = self.env.ref(
            "company_facilities.view_microsite_content_editor_form_facilities"
        )
        self.assertNotIn("facility_block_enabled", editor_view.arch_db)
        self.assertIn(
            'widget="facility_checkboxes"',
            editor_view.arch_db,
            "the list is checkboxes grouped under their subdivision",
        )
        company_view = self.env.ref("company_facilities.view_company_form_facilities")
        self.assertNotIn("facility_block_enabled", company_view.arch_db)

    def test_the_title_field_says_what_it_is(self):
        field = self.Editor._fields["facility_block_title"]
        self.assertEqual(field.string, "Section title")
        self.assertEqual(field.help, "Leave empty to use the default heading.")
        editor_view = self.env.ref(
            "company_facilities.view_microsite_content_editor_form_facilities"
        )
        self.assertIn('placeholder="Facilities and services"', editor_view.arch_db)

    def test_a_merchant_saves_their_own_ticks_from_the_page_content_screen(self):
        """``res.company`` is writable by ``base.group_erp_manager`` alone.

        If this ever raises ``AccessError`` the screen has quietly turned back
        into the company form, and one person is ticking for 218 shops again.
        """
        editor = self.Editor.with_user(self.merchant).create(
            {
                "facility_ids": [(6, 0, (self.card + self.ramp).ids)],
                "facility_block_title": "Lo que encontrarás",
            }
        )
        editor.action_save()
        self.assertEqual(self.company.facility_ids, self.ramp + self.card)
        self.assertEqual(self.company.facility_block_title, "Lo que encontrarás")
        values = self.Editor.with_user(self.merchant).default_get(
            ["facility_ids", "facility_block_title"]
        )
        self.assertEqual(
            sorted(values["facility_ids"][0][2]), sorted((self.ramp + self.card).ids)
        )
        self.assertEqual(values["facility_block_title"], "Lo que encontrarás")

    def test_a_merchant_can_untick_everything_and_the_section_goes(self):
        self.company.facility_ids = self.ramp
        editor = self.Editor.with_user(self.merchant).create(
            {"facility_ids": [(5, 0, 0)]}
        )
        editor.action_save()
        self.assertFalse(self.company.facility_ids)
        self.assertNotIn("o_cf_facilities", self._render_homepage())
