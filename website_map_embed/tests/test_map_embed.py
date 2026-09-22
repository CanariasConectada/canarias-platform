# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMapEmbed(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Partner = cls.env["res.partner"]

    def _render(self, values):
        return str(self.env["ir.qweb"]._render("website_map_embed.map_iframe", values))

    def test_url_is_byte_identical_to_the_historical_microsite_one(self):
        # street, city, zip in that order, no street2: the URL the 218
        # microsites already publish must not change with the refactor.
        partner = self.Partner.create(
            {
                "name": "Plaza Venue",
                "street": "Calle Mayor 1",
                "street2": "Local 3",
                "zip": "35200",
                "city": "Telde",
            }
        )
        self.assertEqual(
            partner._canarias_map_embed_url(),
            "https://maps.google.com/maps?q=Calle+Mayor+1+Telde+35200"
            "&z=13&ie=UTF8&output=embed",
        )

    def test_special_characters_are_encoded(self):
        partner = self.Partner.create(
            {
                "name": "Odd Venue",
                "street": "Calle Ñ & Co 5%",
                "city": 'Telde "La Vega"',
            }
        )
        self.assertEqual(
            partner._canarias_map_embed_url(),
            "https://maps.google.com/maps?q=Calle+%C3%91+%26+Co+5%25+Telde+%22La+Vega%22"
            "&z=13&ie=UTF8&output=embed",
        )

    def test_city_alone_is_enough(self):
        partner = self.Partner.create({"name": "Town Hall", "city": "Arucas"})
        self.assertIn("q=Arucas&", partner._canarias_map_embed_url())

    def test_zip_alone_keeps_the_historical_behaviour(self):
        partner = self.Partner.create({"name": "Postcode Only", "zip": "35200"})
        self.assertIn("q=35200&", partner._canarias_map_embed_url())

    def test_name_only_venue_gives_no_url(self):
        partner = self.Partner.create({"name": "Somewhere"})
        self.assertFalse(partner._canarias_map_embed_url())

    def test_blank_address_parts_give_no_url(self):
        partner = self.Partner.create({"name": "Blank", "street": "  ", "city": " "})
        self.assertFalse(partner._canarias_map_embed_url())

    def test_custom_zoom(self):
        partner = self.Partner.create({"name": "Zoomed", "city": "Telde"})
        self.assertIn("&z=16&", partner._canarias_map_embed_url(zoom=16))

    def test_template_responsive_box_by_default(self):
        partner = self.Partner.create({"name": "Render", "street": "Calle Uno 2"})
        html = self._render(
            {"map_url": partner._canarias_map_embed_url(), "map_title": "Venue"}
        )
        self.assertIn("<iframe", html)
        self.assertIn("output=embed", html)
        self.assertIn("ratio-16x9", html)
        self.assertIn('loading="lazy"', html)
        self.assertIn('title="Venue"', html)
        self.assertNotIn("height=", html)

    def test_template_fixed_height_mode(self):
        partner = self.Partner.create({"name": "Render", "street": "Calle Uno 2"})
        html = self._render(
            {"map_url": partner._canarias_map_embed_url(), "map_height": 240}
        )
        self.assertIn('height="240"', html)
        self.assertIn('width="100%"', html)
        self.assertNotIn("ratio-16x9", html)

    def test_template_renders_nothing_without_url(self):
        self.assertNotIn("<iframe", self._render({"map_url": False}))
