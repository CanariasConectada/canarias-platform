# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests.common import BaseCase

from ..tools.opening_hours import parse_opening_hours


class TestOpeningHoursParser(BaseCase):
    """Pure parser tests: no database involved."""

    def test_empty_values(self):
        self.assertEqual(parse_opening_hours(None), {})
        self.assertEqual(parse_opening_hours(""), {})
        self.assertEqual(parse_opening_hours("   "), {})

    def test_single_range(self):
        parsed = parse_opening_hours("L-V 08:00-14:00")
        # Monday (0) through Friday (4), one range each.
        self.assertEqual(sorted(parsed), [0, 1, 2, 3, 4])
        self.assertEqual(parsed[0], [("08:00", "14:00")])

    def test_split_shift_and_saturday(self):
        parsed = parse_opening_hours(
            "L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00"
        )
        self.assertEqual(parsed[0], [("10:00", "13:30"), ("16:30", "20:00")])
        self.assertEqual(parsed[5], [("10:00", "14:00")])
        self.assertNotIn(6, parsed)

    def test_comma_and_dash_lists(self):
        self.assertEqual(sorted(parse_opening_hours("L,X,V 09:00-13:00")), [0, 2, 4])
        self.assertEqual(
            sorted(parse_opening_hours("L-M-X-J 09:00-13:00")), [0, 1, 2, 3]
        )

    def test_invalid_values(self):
        self.assertIsNone(parse_opening_hours("whenever we feel like it"))
        self.assertIsNone(parse_opening_hours("Z-V 08:00-14:00"))
        self.assertIsNone(parse_opening_hours("L-V 8h-14h"))
        # Reversed range (V-L) is rejected instead of guessed.
        self.assertIsNone(parse_opening_hours("V-L 08:00-14:00"))
