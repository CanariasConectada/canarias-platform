# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, tagged

# The notice's own class: asserting the wording would break on a CI database
# rendering another language.
NOTICE = "o_wec_past_notice"


@tagged("post_install", "-at_install")
class TestPastEventsFallback(HttpCase):
    """/event falls back to the history instead of an empty page.

    Asked for on 2026-08-18: the neighbourhoods' events are bursts — between
    bursts the legacy page still showed what had been held, the default
    Odoo page shows nothing.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        now = fields.Datetime.now()
        cls.past_event = cls.env["event.event"].create(
            {
                "name": "WEC Feria del Barrio",
                "date_begin": now - timedelta(days=30),
                "date_end": now - timedelta(days=29),
                "website_published": True,
            }
        )

    def _upcoming(self):
        now = fields.Datetime.now()
        return self.env["event.event"].create(
            {
                "name": "WEC Mercadillo Nocturno",
                "date_begin": now + timedelta(days=7),
                "date_end": now + timedelta(days=8),
                "website_published": True,
            }
        )

    def test_no_upcoming_shows_the_history_and_says_so(self):
        response = self.url_open("/event")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.past_event.name, response.text)
        self.assertIn(NOTICE, response.text)

    def test_an_upcoming_event_keeps_the_default_page(self):
        upcoming = self._upcoming()
        response = self.url_open("/event")
        self.assertEqual(response.status_code, 200)
        self.assertIn(upcoming.name, response.text)
        self.assertNotIn(NOTICE, response.text)

    def test_an_explicit_date_choice_is_honoured_even_empty(self):
        """?date=upcoming with nothing scheduled must stay the empty
        upcoming page: the visitor asked for a range, not for help."""
        response = self.url_open("/event?date=upcoming")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(NOTICE, response.text)
        self.assertNotIn(self.past_event.name, response.text)

    def test_the_explicit_history_page_carries_no_notice(self):
        response = self.url_open("/event?date=old")
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.past_event.name, response.text)
        self.assertNotIn(NOTICE, response.text)
