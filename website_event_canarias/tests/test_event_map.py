# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

# Markup of the core "Get directions" button (website_event
# event_description_full); its href is event._google_map_link().
DIRECTIONS_LINK = 'target="_blank" class="btn btn-light"'


@tagged("post_install", "-at_install")
class TestEventMap(HttpCase):
    """The event page embeds the venue map next to "Get directions"."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.venue = cls.env["res.partner"].create(
            {
                "name": "WEC Plaza de Santiago",
                "street": "Calle Mayor 1",
                "zip": "35200",
                "city": "Telde",
            }
        )
        cls.name_only_venue = cls.env["res.partner"].create(
            {"name": "WEC Salon Parroquial"}
        )

    def _event(self, address):
        now = fields.Datetime.now()
        return self.env["event.event"].create(
            {
                "name": "WEC Verbena %s" % (address.id or "online"),
                "date_begin": now + timedelta(days=7),
                "date_end": now + timedelta(days=8),
                "website_published": True,
                "address_id": address.id,
            }
        )

    def _page(self, event):
        response = self.url_open(event.website_url)
        self.assertEqual(response.status_code, 200)
        return response.text

    def test_street_address_embeds_the_map(self):
        html = self._page(self._event(self.venue))
        self.assertIn("output=embed", html)
        self.assertIn("Calle+Mayor+1", html)
        self.assertIn("o_wec_event_map", html)
        # The core "Get directions" link is kept (its label is translated,
        # so match its markup), the map only comes before it.
        self.assertIn(DIRECTIONS_LINK, html)
        self.assertLess(html.index("o_wec_event_map"), html.index(DIRECTIONS_LINK))

    def test_name_only_venue_shows_no_map(self):
        # The site layout carries iframes of its own (support widget), so
        # only the map markup is asserted absent.
        html = self._page(self._event(self.name_only_venue))
        self.assertNotIn("o_wec_event_map", html)
        self.assertNotIn("output=embed", html)
        self.assertIn(DIRECTIONS_LINK, html)

    def test_online_event_without_address_shows_no_map(self):
        html = self._page(self._event(self.env["res.partner"]))
        self.assertNotIn("o_wec_event_map", html)
        self.assertNotIn("output=embed", html)
        self.assertNotIn(DIRECTIONS_LINK, html)
