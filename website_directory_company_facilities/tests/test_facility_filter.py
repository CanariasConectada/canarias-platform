# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.http_routing.tests.common import MockRequest
from odoo.addons.website_directory_company_facilities.controllers.main import (
    WebsiteDirectoryFacilities,
)


@tagged("post_install", "-at_install")
class TestFacilityFilter(TransactionCase):
    """Filter the directory by what a shop actually offers.

    Asked for on 2026-08-16: "en el directorio debemos poder filtrar por
    comercios por instalaciones y servicios".

    The domain building is tested directly rather than through HTTP: what has
    to be right is which shops come back for a given set of ticks, and that
    is a question about a domain, not about a page.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.controller = WebsiteDirectoryFacilities()
        cls.access = cls.env["company.facility.category"].create(
            {"name": "Acceso", "sequence": 1}
        )
        cls.parking_group = cls.env["company.facility.category"].create(
            {"name": "Cómo llegar", "sequence": 2}
        )
        cls.ramp = cls.env["company.facility"].create(
            {"name": "Rampa", "category_id": cls.access.id}
        )
        cls.parking = cls.env["company.facility"].create(
            {"name": "Aparcamiento", "category_id": cls.parking_group.id}
        )
        cls.website = cls.env["website"].search([], limit=1)

    def _domain(self, raw):
        # The controller reads the catalogue through `request.env` -- it has
        # to, because it is checking ids that came off a query string against
        # what really exists. `MockRequest` is core's own way of giving a
        # controller that environment outside an HTTP round trip.
        with MockRequest(self.env, website=self.website):
            return self.controller._get_extra_filter_domain({"facility": raw})

    def test_one_tick_asks_for_that_one_thing(self):
        domain = self._domain(str(self.ramp.id))
        self.assertEqual(domain, [("company_id.facility_ids", "in", [self.ramp.id])])

    def test_two_ticks_narrow_rather_than_widen(self):
        """Both, not either.

        A single ``in`` leaf holding both ids would return a shop with only a
        ramp to somebody who asked for a ramp AND parking, which is the
        opposite of what an amenity filter promises.
        """
        domain = self._domain("%s,%s" % (self.ramp.id, self.parking.id))
        self.assertEqual(
            domain,
            [
                ("company_id.facility_ids", "in", [self.ramp.id]),
                ("company_id.facility_ids", "in", [self.parking.id]),
            ],
        )

    def test_a_hand_typed_address_cannot_break_the_page(self):
        """The query string belongs to whoever holds the address bar."""
        for raw in ("", "abc", "-1", "9999999", "3;4", ",,,"):
            with self.subTest(raw=raw):
                self.assertEqual(
                    self._domain(raw), [], "junk must filter nothing, not raise"
                )

    def test_an_unticked_directory_filters_nothing(self):
        with MockRequest(self.env, website=self.website):
            self.assertEqual(self.controller._get_extra_filter_domain({}), [])

    def test_the_choice_survives_the_pager(self):
        """Page 2 of a filtered directory has to still be filtered."""
        with MockRequest(self.env, website=self.website):
            args = self.controller._get_extra_pager_args(
                {"facility": "%s,%s" % (self.ramp.id, self.parking.id)}
            )
        self.assertEqual(args["facility"], "%s,%s" % (self.ramp.id, self.parking.id))

    def test_toggling_one_chip_keeps_every_other_filter(self):
        """Clicking "parking" must not throw away the search box.

        The address is built on the server precisely so that a chip cannot
        quietly reset the rest of the panel.
        """
        url = self.controller._facility_url(
            "/comercio",
            {"search": "muebles", "category": "12", "facility": str(self.ramp.id)},
            [self.ramp.id, self.parking.id],
        )
        self.assertIn("search=muebles", url)
        self.assertIn("category=12", url)
        self.assertIn("facility=%s%%2C%s" % (self.ramp.id, self.parking.id), url)

    def test_changing_the_filter_goes_back_to_the_first_page(self):
        url = self.controller._facility_url(
            "/comercio", {"page": "7", "search": "muebles"}, [self.ramp.id]
        )
        self.assertNotIn("page=", url)

    def test_clearing_leaves_the_rest_of_the_directory_alone(self):
        url = self.controller._facility_url(
            "/comercio", {"search": "muebles", "facility": str(self.ramp.id)}, []
        )
        self.assertEqual(url, "/comercio?search=muebles")

    def test_an_empty_listing_still_offers_the_whole_panel(self):
        """A filter combination with zero results must not eat the panel.

        Originally about the chips being derived from the result set (a
        certification or a search matching nothing would derive an empty
        panel, Asked for on 2026-08-18: "Desaparece el filtro de abajo cuando
        colocas sostenibilidad"). The panel is now the whole active catalogue
        UNCONDITIONALLY (2026-08-21: as of that date only 1 of 216 companies
        had ANY facility assigned, so deriving from real adoption hid whole
        categories nobody had picked yet, "Familia y mascotas" included), so
        this also stands as the regression test for that: neither fixture
        facility is assigned to any company, and both must still show.
        """
        with MockRequest(self.env, website=self.website):
            pool = self.controller._facility_pool(
                None, {"search": "wdcf-nada-se-llama-asi-9317"}
            )
        self.assertIn(self.ramp, pool)
        self.assertIn(self.parking, pool)

    def test_an_archived_category_or_facility_never_shows(self):
        """The one gate the whole-catalogue pool still respects.

        Two distinct ways in: a facility archived on its own, and a facility
        whose CATEGORY is archived (the facility itself untouched) -- the
        panel must drop both, the same way it always excluded them from a
        shop's own listing.
        """
        archived_facility = self.env["company.facility"].create(
            {"name": "WDCF Archivada", "category_id": self.access.id, "active": False}
        )
        archived_category = self.env["company.facility.category"].create(
            {"name": "WDCF Categoría archivada", "sequence": 3, "active": False}
        )
        orphaned_facility = self.env["company.facility"].create(
            {"name": "WDCF Huérfana", "category_id": archived_category.id}
        )
        with MockRequest(self.env, website=self.website):
            pool = self.controller._facility_pool(None, {})
        self.assertNotIn(archived_facility, pool)
        self.assertNotIn(orphaned_facility, pool)

    def test_groups_split_selection_from_offer(self):
        """The template hangs the dropdown on the unselected entries and the
        pills on the selected ones; the controller must mark each entry."""
        with MockRequest(self.env, website=self.website):
            groups = self.controller._facility_filter_groups(
                [self.ramp.id], None, "/comercio", {"facility": str(self.ramp.id)}
            )
        by_name = {
            entry["name"]: entry for group in groups for entry in group["facilities"]
        }
        self.assertTrue(by_name["Rampa"]["selected"])
        self.assertFalse(by_name["Aparcamiento"]["selected"])
