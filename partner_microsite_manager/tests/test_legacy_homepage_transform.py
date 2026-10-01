# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo.tests.common import BaseCase

from ..tools import legacy_homepage
from ..tools.legacy_homepage import address_similarity, relink_live_data

FACTS = {"address": True, "phone": True, "email": True, "hours": True, "map": True}
LIVE = {
    "email": "shop@example.com",
    "address": "Calle Nueva 5, 35010 Las Palmas",
    "website": "",
    "map": "",
    "map_explicit": False,
}
PHONE_CALL = legacy_homepage.LIVE_TEMPLATES["phone"]


def page(contact="", features="", extra=""):
    return (
        '<t t-name="website.homepage_x"><div id="wrap">'
        f"{features}"
        '<section data-name="Formulario"><div class="row"><div class="col-lg-6">'
        '<iframe src="https://maps.google.com/maps?q=Old&amp;output=embed" height="200"/>'
        f"{contact}"
        "</div></div></section>"
        f"{extra}"
        "</div></t>"
    )


PHONE_LINE = '<p class="mb-2"><i class="fa fa-phone fa-fw"/>928 00 00 00</p>'
ADDRESS_LINE = '<p class="mb-2"><i class="fa fa-map-marker fa-fw"/>Calle Nueva 5</p>'
HORARIO = (
    '<section data-name="Horario"><div class="container"><div class="row">'
    '<div class="col-lg-4"><span class="fa fa-clock-o"/><h5>Time</h5>'
    '<t t-call="partner_microsite_manager.microsite_opening_hours_card"/></div>'
    '<div class="col-lg-4"><span class="fa fa-map-marker"/><h5>Parking</h5>'
    '<p class="text-muted">Near</p></div>'
    '<div class="col-lg-4"><span class="fa fa-truck"/><h5>Delivery</h5>'
    '<p class="text-muted">Yes</p></div>'
    "{extra}</div></div></section>"
)


class TestLegacyHomepageTransform(BaseCase):
    """The pure transformation: no database involved."""

    def _run(self, arch, **kwargs):
        kwargs.setdefault("live", LIVE)
        new_arch, report = relink_live_data(arch, FACTS, **kwargs)
        return etree.fromstring((new_arch or arch).encode()), report

    def test_a_line_with_several_icons_is_left_alone(self):
        multi = (
            '<div class="mb-2"><i class="fa fa-phone fa-fw"/>928 00 00 00 '
            '<i class="fa fa-envelope fa-fw"/>old@example.com</div>'
        )
        tree, report = self._run(page(ADDRESS_LINE + multi))
        self.assertIn("928 00 00 00", etree.tostring(tree, encoding="unicode"))
        self.assertIn("line with several icons left as is", report["notes"])
        self.assertNotIn("phone", report["relinked"])

    def test_a_labelled_line_is_left_alone(self):
        labelled = (
            '<p class="mb-2"><i class="fa fa-phone fa-fw"/>'
            "<strong>Shop:</strong> 928 00 00 00</p>"
        )
        tree, report = self._run(page(ADDRESS_LINE + labelled))
        self.assertIn(
            "<strong>Shop:</strong> 928 00 00 00",
            etree.tostring(tree, encoding="unicode"),
        )
        self.assertIn("labelled phone line left as is", report["notes"])

    def test_only_the_first_contact_section_is_touched(self):
        second = (
            '<section data-name="Formulario"><div>'
            '<iframe src="https://maps.google.com/maps?q=Second" height="100"/>'
            '<p class="mb-2"><i class="fa fa-phone fa-fw"/>600 00 00 00</p>'
            "</div></section>"
        )
        tree, report = self._run(page(ADDRESS_LINE + PHONE_LINE, extra=second))
        text = etree.tostring(tree, encoding="unicode")
        self.assertIn("600 00 00 00", text)
        self.assertIn("q=Second", text)
        self.assertNotIn("928 00 00 00", text)
        self.assertEqual(text.count(PHONE_CALL), 1)

    def test_a_horario_section_with_more_columns_keeps_them_visible(self):
        extra = '<div class="col-lg-4"><h5>Our own card</h5></div>'
        tree, report = self._run(
            page(ADDRESS_LINE + PHONE_LINE, features=HORARIO.format(extra=extra))
        )
        section = tree.xpath("//section[@data-name='Horario']")[0]
        self.assertIsNone(section.get("t-if"))
        self.assertIn("Horario section has other content: no t-if", report["notes"])
        columns = section.xpath(".//div[@t-if]")
        self.assertEqual(len(columns), 3)

    def test_a_horario_section_with_only_the_cards_gets_its_t_if(self):
        tree, report = self._run(
            page(
                ADDRESS_LINE + PHONE_LINE,
                features=HORARIO.format(extra="<!-- note -->"),
            )
        )
        section = tree.xpath("//section[@data-name='Horario']")[0]
        self.assertIn("'features'", section.get("t-if"))

    def test_comments_and_cdata_are_harmless(self):
        commented = (
            '<p class="mb-2"><i class="fa fa-phone fa-fw"/><!-- old -->928 00 00 00</p>'
        )
        arch = page(
            ADDRESS_LINE + commented,
            extra="<script><![CDATA[ var a = 1 < 2; ]]></script>",
        )
        new_arch, report = relink_live_data(arch, FACTS, live=LIVE)
        self.assertIn(PHONE_CALL, new_arch)
        self.assertNotIn("928 00 00 00", new_arch)
        self.assertIn("var a = 1", new_arch)
        again, _report = relink_live_data(new_arch, FACTS, live=LIVE)
        self.assertIsNone(again)

    def test_a_builder_save_keeps_static_lines_static(self):
        arch = page(ADDRESS_LINE + PHONE_LINE)
        new_arch, report = relink_live_data(arch, FACTS)  # guard: no live
        self.assertIn(PHONE_CALL, new_arch)  # phone always follows the shop
        self.assertIn("Calle Nueva 5</p>", new_arch)
        self.assertIn("q=Old", new_arch)

    def test_a_forced_kind_goes_live_whatever_it_shows(self):
        arch = page('<p class="mb-2"><i class="fa fa-envelope fa-fw"/>x@y.z</p>')
        new_arch, report = relink_live_data(arch, FACTS, force={"email", "map"})
        self.assertIn(legacy_homepage.LIVE_TEMPLATES["email"], new_arch)
        self.assertIn("_get_microsite_map_url", new_arch)

    def test_address_similarity(self):
        self.assertGreaterEqual(
            address_similarity(
                "C/ Republica Dominicana, 23 - 35010 Las Palmas",
                "Calle República Dominicana 23, 35010 Las Palmas de Gran Canaria",
            ),
            0.6,
        )
        self.assertLess(
            address_similarity(
                "Paseo Tomás Morales, 72, Las Palmas de Gran Canaria, 35003",
                "Calle Pascal 9, 35010 Las Palmas de Gran Canaria",
            ),
            0.6,
        )
