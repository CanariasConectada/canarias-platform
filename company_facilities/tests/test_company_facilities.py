# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestCompanyFacilities(TransactionCase):
    """What a shop offers, grouped and in order, on its own microsite.

    Asked for on 2026-08-16: "lo vamos a llamar ahora Instalaciones y
    servicios […] con todo el tema de subdivisiones e iconos y demás que lo
    pueda definir el cliente y nosotros".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.ref("base.main_company")
        cls.Category = cls.env["company.facility.category"]
        cls.Facility = cls.env["company.facility"]
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

    def test_the_starter_catalogue_is_there_to_pick_from(self):
        seeded = self.env.ref("company_facilities.facility_step_free_access")
        self.assertTrue(seeded.exists())
        self.assertEqual(
            seeded.category_id,
            self.env.ref("company_facilities.category_accessibility"),
        )

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

    def test_the_block_renders_what_the_shop_ticked(self):
        self.company.facility_ids = self.ramp + self.card
        self.company.facility_block_title = "Instalaciones y servicios"
        rendered = self.env["ir.qweb"]._render(
            "company_facilities.facilities_block", {"cf_company": self.company}
        )
        self.assertIn("Instalaciones y servicios", rendered)
        self.assertIn("Rampa", rendered)
        self.assertIn("Tarjeta", rendered)
        self.assertIn("fa-credit-card", rendered)

    def test_the_block_falls_back_to_a_heading_when_none_is_given(self):
        self.company.facility_ids = self.ramp
        self.company.facility_block_title = False
        rendered = self.env["ir.qweb"]._render(
            "company_facilities.facilities_block", {"cf_company": self.company}
        )
        self.assertIn("Facilities and services", rendered)

    def test_the_block_stays_off_until_the_shop_asks_for_it(self):
        """218 microsites belong to somebody else.

        The switch is what makes "leave only abinformatica with test content"
        a setting rather than a promise.
        """
        self.assertFalse(self.company.facility_block_enabled)

    def test_the_block_reaches_a_homepage_built_in_the_website_builder(self):
        """None of the 219 migrated homepages calls the microsite template.

        Attaching the block to ``microsite_homepage_content`` alone meant it
        rendered nowhere at all, which is what "no lo veo habilitado" was.
        """
        view = self.env["ir.ui.view"].search(
            [("key", "=", "company_facilities.layout_facilities")], limit=1
        )
        self.assertTrue(view, "the block has to hang off the site layout")
        self.assertEqual(view.inherit_id.key, "website.layout")
        self.assertIn("facility_block_enabled", view.arch_db)
