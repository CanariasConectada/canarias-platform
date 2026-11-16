# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import importlib.util
import os

from odoo import SUPERUSER_ID, api
from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import BaseCase, TransactionCase, new_test_user

from ..tools.opening_hours import (
    find_slot_problem,
    float_to_hhmm,
    format_opening_hours,
    hhmm_to_float,
    parse_opening_hours,
    slots_from_parsed,
)

# Real values from production (2026-09-15), the odd ones included: a
# duplicated day (``S,S``), blocks out of order, unpadded hours, ``23:59``.
PROD_SAMPLES = [
    "L-V 09:00-14:00 / L-V 16:00-20:00",
    "L-V 09:00-17:00 / S 10:00-12:00",
    "L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00",
    "L,M,X,J 15:30-20:30 / V 15:30-19:30",
    "L-M-X-J-V-S 10:30-14:00",
    "X-J-V-S 13:00-23:00",
    "L-V 16:00-20:00 / L-V 09:30-13:30",
    "L,M,X,J,V,S,D 09:00-23:30",
    "L,M,X,J,V,S 10:30-14:00 / L-V 17:00-21:00 / S 17:00-20:00",
    "L,M,X,J 08:00-14:30 / V 08:00-14:00 / V 17:00-20:00 / S,S 08:00-13:30",
    "L-V 08:30-16:30 / X,J,V 19:00-23:59 / S,D 00:00-02:00 / S 13:00-23:59 / D 13:00-23:00",
    "L 09:00-18:00 / M 9:00-13:00 / M 15:00-20:00 / X 09:00-18:00 / J 9:00-13:00 / J 15:00-20:00 / V 09:00-13:00",
    "X-S 17:00-23:30 / D 13:00-16:00 / D 19:00-23:30",
]


def _normalised(parsed):
    """Parser output with padded, sorted, de-duplicated ranges per day."""
    return {
        day: sorted(
            {
                (float_to_hhmm(hhmm_to_float(s)), float_to_hhmm(hhmm_to_float(e)))
                for s, e in ranges
            }
        )
        for day, ranges in parsed.items()
    }


class TestOpeningHoursFormatter(BaseCase):
    """Pure helpers: no database involved."""

    def test_minutes_survive_the_float(self):
        self.assertEqual(float_to_hhmm(hhmm_to_float("23:59")), "23:59")
        self.assertEqual(float_to_hhmm(hhmm_to_float("09:30")), "09:30")
        self.assertEqual(float_to_hhmm(hhmm_to_float("9:05")), "09:05")
        self.assertEqual(hhmm_to_float("09:30"), 9.5)

    def test_canonical_text_is_the_one_merchants_already_type(self):
        slots = [(d, 9.0, 14.0) for d in range(5)] + [(d, 16.0, 20.0) for d in range(5)]
        slots.append((5, 10.0, 13.0))
        self.assertEqual(
            format_opening_hours(slots),
            "L-V 09:00-14:00 / L-V 16:00-20:00 / S 10:00-13:00",
        )
        self.assertEqual(format_opening_hours([]), "")
        # Non-consecutive days with the same hours are separate blocks, and
        # a run of two days is still a range the parser reads.
        self.assertEqual(
            format_opening_hours([(0, 9.0, 13.0), (2, 9.0, 13.0), (3, 9.0, 13.0)]),
            "L 09:00-13:00 / X-J 09:00-13:00",
        )

    def test_every_production_value_round_trips(self):
        for text in PROD_SAMPLES:
            with self.subTest(text=text):
                parsed = parse_opening_hours(text)
                self.assertIsNotNone(parsed)
                regenerated = format_opening_hours(slots_from_parsed(parsed))
                self.assertEqual(
                    _normalised(parse_opening_hours(regenerated)), _normalised(parsed)
                )
                # Canonical text is a fixed point.
                self.assertEqual(
                    format_opening_hours(
                        slots_from_parsed(parse_opening_hours(regenerated))
                    ),
                    regenerated,
                )

    def test_duplicated_day_collapses(self):
        parsed = parse_opening_hours("S,S 08:00-13:30")
        self.assertEqual(slots_from_parsed(parsed), [(5, 8.0, 13.5)])

    def test_problems(self):
        self.assertIsNone(find_slot_problem([(0, 9.0, 14.0), (0, 14.0, 20.0)]))
        self.assertEqual(find_slot_problem([(0, 14.0, 9.0)])[0], "order")
        self.assertEqual(find_slot_problem([(0, 9.0, 9.0)])[0], "order")
        self.assertEqual(find_slot_problem([(0, 9.0, 24.5)])[0], "order")
        self.assertEqual(
            find_slot_problem([(0, 9.0, 14.0), (0, 13.0, 20.0)])[0], "overlap"
        )
        # Same times on another day are no overlap.
        self.assertIsNone(find_slot_problem([(0, 9.0, 14.0), (1, 9.0, 14.0)]))


@tagged("post_install", "-at_install")
class TestOpeningSlots(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Slots Shop"})
        cls.website = cls.env["website"].create(
            {"name": "Slots Shop site", "company_id": cls.company.id}
        )
        cls.company.website_id = cls.website
        cls.Slot = cls.env["microsite.opening.slot"]

    def _slot(self, weekday, open_time, close_time, company=None):
        return self.Slot.create(
            {
                "company_id": (company or self.company).id,
                "weekday": str(weekday),
                "open_time": open_time,
                "close_time": close_time,
            }
        )

    def test_rows_generate_the_text_the_templates_read(self):
        for day in range(5):
            self._slot(day, 9.0, 14.0)
            self._slot(day, 16.0, 20.0)
        self._slot(5, 10.0, 13.0)
        self.assertEqual(
            self.company.microsite_opening_hours,
            "L-V 09:00-14:00 / L-V 16:00-20:00 / S 10:00-13:00",
        )
        rows = self.company._get_microsite_opening_hours_rows()
        self.assertEqual([r[0] for r in rows], [0, 1, 2, 3, 4, 5])
        self.assertEqual(rows[0][2], "09:00 - 14:00 / 16:00 - 20:00")

    def test_editing_a_row_regenerates_the_text(self):
        slot = self._slot(0, 9.0, 14.0)
        self.assertEqual(self.company.microsite_opening_hours, "L 09:00-14:00")
        slot.close_time = 15.5
        self.assertEqual(self.company.microsite_opening_hours, "L 09:00-15:30")
        slot.unlink()
        # Deleting the last row means no hours, on the company form too.
        self.assertFalse(self.company.microsite_opening_hours)
        self.assertEqual(self.company._get_microsite_opening_hours_rows(), [])

    def test_deleting_one_of_several_rows_keeps_the_rest(self):
        first = self._slot(0, 9.0, 14.0)
        self._slot(1, 9.0, 14.0)
        first.unlink()
        self.assertEqual(self.company.microsite_opening_hours, "M 09:00-14:00")

    def test_free_text_still_works_without_rows(self):
        self.company.microsite_opening_hours = "L-V 10:00-14:00"
        self.assertEqual(self.company.microsite_opening_hours, "L-V 10:00-14:00")
        with self.assertRaises(ValidationError):
            self.company.microsite_opening_hours = "whenever"

    def test_more_than_two_periods_a_day_is_fine_with_rows(self):
        for open_time, close_time in ((8.0, 10.0), (11.0, 13.0), (15.0, 17.0)):
            self._slot(0, open_time, close_time)
        self.assertEqual(
            self.company.microsite_opening_hours,
            "L 08:00-10:00 / L 11:00-13:00 / L 15:00-17:00",
        )

    def test_a_row_must_open_before_it_closes(self):
        with self.assertRaises(ValidationError):
            self._slot(0, 14.0, 9.0)
        with self.assertRaises(ValidationError):
            self._slot(0, 9.0, 9.0)

    def test_rows_of_a_day_must_not_overlap(self):
        self._slot(0, 9.0, 14.0)
        with self.assertRaises(ValidationError):
            self._slot(0, 13.0, 20.0)
        # Touching is fine, and so is the same window on another day.
        self._slot(0, 14.0, 20.0)
        self._slot(1, 9.0, 14.0)

    def test_sync_from_text_creates_the_rows_once(self):
        self.company.microsite_opening_hours = "L,M,X,J 15:30-20:30 / V 15:30-19:30"
        synced, unparsed = self.company._sync_slots_from_text()
        self.assertEqual(synced, self.company)
        self.assertFalse(unparsed)
        self.assertEqual(len(self.company.microsite_opening_slot_ids), 5)
        # Regenerated in the canonical form, same schedule.
        self.assertEqual(
            self.company.microsite_opening_hours,
            "L-J 15:30-20:30 / V 15:30-19:30",
        )
        # Idempotent.
        synced, unparsed = self.company._sync_slots_from_text()
        self.assertFalse(synced)
        self.assertFalse(unparsed)
        self.assertEqual(len(self.company.microsite_opening_slot_ids), 5)

    def test_sync_from_text_reports_what_it_cannot_convert(self):
        # The constraint never lets such a text in through the ORM; it is
        # what an old row could hold, so it is put there the way old data
        # sits: in the column.
        self.env.cr.execute(
            "UPDATE res_company SET microsite_opening_hours = %s WHERE id = %s",
            ("Martes: 09:30 - 13:30", self.company.id),
        )
        self.company.invalidate_recordset(["microsite_opening_hours"])
        other = self.env["res.company"].create(
            {
                "name": "Overlap Shop",
                "microsite_opening_hours": "L 09:00-14:00 / L 12:00-18:00",
            }
        )
        empty = self.env["res.company"].create({"name": "No Hours Shop"})
        synced, unparsed = (self.company | other | empty)._sync_slots_from_text()
        self.assertFalse(synced)
        self.assertEqual(unparsed, self.company | other)
        self.assertEqual(self.company.microsite_opening_hours, "Martes: 09:30 - 13:30")
        self.assertFalse(self.company.microsite_opening_slot_ids)
        self.assertFalse(other.microsite_opening_slot_ids)

    def test_a_merchant_reads_but_does_not_write_rows_directly(self):
        merchant = new_test_user(
            self.env,
            login="slots_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=self.company.id,
            company_ids=[(6, 0, self.company.ids)],
        )
        slot = self._slot(0, 9.0, 14.0)
        self.assertEqual(slot.with_user(merchant).open_time, 9.0)
        with self.assertRaises(AccessError):
            slot.with_user(merchant).write({"open_time": 10.0})
        with self.assertRaises(AccessError):
            self.Slot.with_user(merchant).create(
                {"company_id": self.company.id, "weekday": "1", "open_time": 9, "close_time": 14}
            )

    # ------------------------------------------------------------------
    # The page
    # ------------------------------------------------------------------
    def _render(self, template="partner_microsite_manager.microsite_homepage_content"):
        return str(self.env["ir.qweb"]._render(template, {"website": self.website}))

    def test_the_homepage_shows_the_rows(self):
        self._slot(0, 9.0, 14.0)
        self._slot(0, 16.0, 20.0)
        html = self._render()
        self.assertIn("Opening Hours", html)
        self.assertIn("09:00 - 14:00 / 16:00 - 20:00", html)
        self.assertIn('data-hours-row="0"', html)
        self.assertNotIn('data-hours-row="1"', html)

    def test_the_card_renders_on_its_own_and_hides_without_hours(self):
        card = "partner_microsite_manager.microsite_opening_hours_card"
        self.assertNotIn("o_microsite_hours", self._render(card))
        self._slot(2, 10.0, 13.0)
        html = self._render(card)
        self.assertIn("o_microsite_hours", html)
        self.assertIn("10:00 - 13:00", html)

    def test_the_legacy_homepage_card_is_relinked_to_the_company(self):
        legacy_arch = (
            '<t t-name="website.homepage_slots"><div id="wrap" class="oe_structure oe_empty">'
            '<section data-name="Horario"><div class="col-lg-4 pt16 pb16 text-center">'
            '<h5 class="fw-bold">Horario</h5>'
            '<div class="horario-card-accordion mt-3" style="text-align: left;">'
            "<span>Lunes</span><span>09:30 - 13:30</span><script>var x = 1;</script>"
            "</div><p>after the card</p></div></section>"
            "<section data-name=\"Texto\"><p>The merchant's own words</p></section>"
            "</div></t>"
        )
        view = self.env["ir.ui.view"].create(
            {
                "name": "Home - Slots Shop",
                "type": "qweb",
                "key": "website.homepage_slots",
                "arch_db": legacy_arch,
                "website_id": self.website.id,
            }
        )
        self.env["website.page"].create(
            {
                "name": "Home - Slots Shop",
                "url": "/",
                "view_id": view.id,
                "website_id": self.website.id,
                "is_published": True,
            }
        )
        self._slot(0, 8.0, 12.0)

        relinked = self.company._relink_legacy_opening_hours_card()

        self.assertEqual(relinked, self.company)
        arch = view.arch_db
        self.assertNotIn("horario-card-accordion", arch)
        self.assertNotIn("09:30 - 13:30", arch)
        self.assertIn('t-call="partner_microsite_manager.microsite_opening_hours_card"', arch)
        # Everything around the card is untouched.
        self.assertIn("<p>after the card</p>", arch)
        self.assertIn("The merchant's own words", arch)
        self.assertIn('<h5 class="fw-bold">Horario</h5>', arch)
        html = str(self.env["ir.qweb"]._render(view.id, {"website": self.website}))
        self.assertIn("08:00 - 12:00", html)
        self.assertNotIn("09:30 - 13:30", html)
        # Idempotent: nothing left to swap.
        self.assertFalse(self.company._relink_legacy_opening_hours_card())
        self.assertEqual(view.arch_db, arch)

    def test_the_relink_keeps_the_translations_of_the_rest_of_the_page(self):
        """Only the base arch is rewritten; the other languages re-map the
        terms that did not change. The platform serves seven languages."""
        self.env["res.lang"]._activate_lang("es_ES")
        view = self.env["ir.ui.view"].create(
            {
                "name": "Home - translated",
                "type": "qweb",
                "key": "website.homepage_translated",
                "arch_db": (
                    '<t t-name="website.homepage_translated"><div id="wrap">'
                    "<h5>Opening hours</h5>"
                    '<div class="horario-card-accordion"><span>Monday</span></div>'
                    "<p>Our story</p></div></t>"
                ),
                "website_id": self.website.id,
            }
        )
        self.env["website.page"].create(
            {"name": "Home", "url": "/", "view_id": view.id, "website_id": self.website.id}
        )
        view.update_field_translations(
            "arch_db", {"es_ES": {"Opening hours": "Horario", "Our story": "Nuestra historia"}}
        )
        self.assertEqual(self.company._relink_legacy_opening_hours_card(), self.company)
        spanish = view.with_context(lang="es_ES").arch_db
        self.assertIn("<h5>Horario</h5>", spanish)
        self.assertIn("<p>Nuestra historia</p>", spanish)
        self.assertIn('t-call="partner_microsite_manager.microsite_opening_hours_card"', spanish)
        self.assertNotIn("horario-card-accordion", spanish)
        self.assertIn("<h5>Opening hours</h5>", view.with_context(lang="en_US").arch_db)

    def test_a_broken_homepage_does_not_take_the_others_down(self):
        """One page lxml refuses is logged and skipped; the next one is done."""
        broken = self.env["res.company"].create({"name": "Broken Shop"})
        broken.website_id = self.env["website"].create(
            {"name": "Broken", "company_id": broken.id}
        )
        view = self.env["ir.ui.view"].create(
            {
                "name": "Home - broken",
                "type": "qweb",
                "key": "website.homepage_broken",
                "arch_db": '<t t-name="website.homepage_broken"><div>ok</div></t>',
                "website_id": broken.website_id.id,
            }
        )
        self.env["website.page"].create(
            {"name": "Home", "url": "/", "view_id": view.id, "website_id": broken.website_id.id}
        )
        # Straight into the column, the way an importer would have left it.
        self.env.cr.execute(
            "UPDATE ir_ui_view SET arch_db = jsonb_build_object('en_US', %s) WHERE id = %s",
            ('<div class="horario-card-accordion"><p>unclosed</div>', view.id),
        )
        view.invalidate_recordset()
        good_view = self.env["ir.ui.view"].create(
            {
                "name": "Home - good",
                "type": "qweb",
                "key": "website.homepage_good",
                "arch_db": (
                    '<t t-name="website.homepage_good"><div id="wrap">'
                    '<div class="horario-card-accordion"><span>x</span></div></div></t>'
                ),
                "website_id": self.website.id,
            }
        )
        self.env["website.page"].create(
            {"name": "Home", "url": "/", "view_id": good_view.id, "website_id": self.website.id}
        )
        with self.assertLogs("odoo.addons.partner_microsite_manager.models.res_company", "ERROR"):
            relinked = (broken | self.company)._relink_legacy_opening_hours_card()
        self.assertEqual(relinked, self.company)
        self.assertIn("horario-card-accordion", view.arch_db)
        self.assertNotIn("horario-card-accordion", good_view.arch_db)

    def test_the_post_migration_runs_end_to_end(self):
        """The script itself, not only the helpers it calls."""
        self.company.microsite_opening_hours = "L-V 09:00-14:00"
        view = self.env["ir.ui.view"].create(
            {
                "name": "Home - migrated",
                "type": "qweb",
                "key": "website.homepage_migrated",
                "arch_db": (
                    '<t t-name="website.homepage_migrated"><div id="wrap">'
                    '<div class="horario-card-accordion"><span>Lunes</span></div></div></t>'
                ),
                "website_id": self.website.id,
            }
        )
        self.env["website.page"].create(
            {"name": "Home", "url": "/", "view_id": view.id, "website_id": self.website.id}
        )
        path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "migrations", "19.0.2.8.0", "post-migration.py",
        )
        spec = importlib.util.spec_from_file_location("pmm_post_migration", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.migrate(self.env.cr, "19.0.2.7.2")
        env = api.Environment(self.env.cr, SUPERUSER_ID, {})
        company = env["res.company"].browse(self.company.id)
        self.assertEqual(len(company.microsite_opening_slot_ids), 5)
        self.assertEqual(company.microsite_opening_hours, "L-V 09:00-14:00")
        self.assertIn("microsite_opening_hours_card", env["ir.ui.view"].browse(view.id).arch_db)
        # A fresh install has no version and nothing to migrate.
        module.migrate(self.env.cr, None)

    def test_a_homepage_without_the_card_is_left_alone(self):
        view = self.env["ir.ui.view"].create(
            {
                "name": "Home - plain",
                "type": "qweb",
                "key": "website.homepage_plain",
                "arch_db": '<t t-name="website.homepage_plain"><div id="wrap"><p>Hi</p></div></t>',
                "website_id": self.website.id,
            }
        )
        self.env["website.page"].create(
            {"name": "Home", "url": "/", "view_id": view.id, "website_id": self.website.id}
        )
        self.assertFalse(self.company._relink_legacy_opening_hours_card())
        self.assertIn("<p>Hi</p>", view.arch_db)


@tagged("post_install", "-at_install")
class TestOpeningSlotsEditor(TransactionCase):
    """The merchant's screen: rows in, rows out, text generated."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop = cls.env["res.company"].create({"name": "Editor Shop"})
        cls.shop.website_id = cls.env["website"].create(
            {"name": "Editor Shop", "company_id": cls.shop.id}
        )
        cls.merchant = new_test_user(
            cls.env,
            login="slots_editor_merchant",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=cls.shop.id,
            company_ids=[(6, 0, cls.shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )

    def _editor(self):
        return self.env["microsite.content.editor"].with_user(self.merchant)

    @staticmethod
    def _rows(*rows):
        return [
            (0, 0, {"weekday": str(d), "open_time": o, "close_time": c})
            for d, o, c in rows
        ]

    def test_it_opens_on_the_rows_the_shop_has(self):
        self.env["microsite.opening.slot"].create(
            {"company_id": self.shop.id, "weekday": "3", "open_time": 9, "close_time": 14}
        )
        values = self._editor().default_get(["opening_slot_ids", "microsite_opening_hours"])
        self.assertEqual(
            values["opening_slot_ids"],
            [(0, 0, {"weekday": "3", "open_time": 9.0, "close_time": 14.0})],
        )

    def test_it_opens_on_the_legacy_text_when_the_shop_has_no_rows(self):
        self.shop.sudo().microsite_opening_hours = "L-M 10:00-13:00"
        values = self._editor().default_get(["opening_slot_ids"])
        self.assertEqual(
            values["opening_slot_ids"],
            self._rows((0, 10.0, 13.0), (1, 10.0, 13.0)),
        )

    def test_a_merchant_saves_rows_and_the_page_gets_the_text(self):
        editor = self._editor().create(
            {"opening_slot_ids": self._rows((0, 9, 14), (0, 16, 20), (5, 10, 13))}
        )
        self.assertEqual(
            editor.microsite_opening_hours,
            "L 09:00-14:00 / L 16:00-20:00 / S 10:00-13:00",
        )
        editor.action_save()
        self.assertEqual(len(self.shop.microsite_opening_slot_ids), 3)
        self.assertEqual(
            self.shop.microsite_opening_hours,
            "L 09:00-14:00 / L 16:00-20:00 / S 10:00-13:00",
        )
        html = str(
            self.env["ir.qweb"]._render(
                "partner_microsite_manager.microsite_homepage_content",
                {"website": self.shop.website_id},
            )
        )
        self.assertIn("09:00 - 14:00 / 16:00 - 20:00", html)
        # Saving again replaces, never accumulates.
        self._editor().create({"opening_slot_ids": self._rows((2, 8, 12))}).action_save()
        self.assertEqual(len(self.shop.microsite_opening_slot_ids), 1)
        self.assertEqual(self.shop.microsite_opening_hours, "X 08:00-12:00")

    def test_no_rows_means_no_hours_on_the_page(self):
        self._editor().create({"opening_slot_ids": self._rows((0, 9, 14))}).action_save()
        self._editor().create({"opening_slot_ids": []}).action_save()
        self.assertFalse(self.shop.microsite_opening_slot_ids)
        self.assertFalse(self.shop.microsite_opening_hours)
        self.assertEqual(self.shop._get_microsite_opening_hours_rows(), [])

    def test_saving_something_else_keeps_a_text_that_never_became_rows(self):
        """The migration could not convert this shop; the editor opens with
        an empty list, and saving the banner must not wipe the hours."""
        self.env.cr.execute(
            "UPDATE res_company SET microsite_opening_hours = %s WHERE id = %s",
            ("Martes: 09:30 - 13:30", self.shop.id),
        )
        self.shop.invalidate_recordset(["microsite_opening_hours"])
        values = self._editor().default_get(["opening_slot_ids"])
        self.assertEqual(values["opening_slot_ids"], [])
        self._editor().create({"microsite_intro_title": "Rebajas"}).action_save()
        self.assertEqual(self.shop.microsite_intro_title, "Rebajas")
        self.assertEqual(self.shop.microsite_opening_hours, "Martes: 09:30 - 13:30")

    def test_a_text_that_parses_but_cannot_be_rows_opens_empty_and_survives(self):
        """Company 68 on the prod copy: closes at 01:00, past midnight. The
        migration left its text; the screen must open, empty, and leave it."""
        self.shop.sudo().microsite_opening_hours = "D-L-M-X-J 11:00-23:59 / V-S 11:00-01:00"
        values = self._editor().default_get(["opening_slot_ids"])
        self.assertEqual(values["opening_slot_ids"], [])
        editor = self._editor().create(dict(values, microsite_intro_title="Noche"))
        editor.action_save()
        self.assertEqual(self.shop.microsite_intro_title, "Noche")
        self.assertEqual(
            self.shop.microsite_opening_hours, "D-L-M-X-J 11:00-23:59 / V-S 11:00-01:00"
        )
        self.assertFalse(self.shop.microsite_opening_slot_ids)

    def test_another_merchant_cannot_touch_this_merchants_screen(self):
        """Transient records have no implicit owner rule in Odoo 19."""
        other_shop = self.env["res.company"].create({"name": "Other Shop"})
        other_shop.website_id = self.env["website"].create(
            {"name": "Other Shop", "company_id": other_shop.id}
        )
        intruder = new_test_user(
            self.env,
            login="slots_editor_intruder",
            groups="base.group_user,website.group_website_restricted_editor",
            company_id=other_shop.id,
            company_ids=[(6, 0, other_shop.ids)],
            context={"no_reset_password": True, "tracking_disable": True},
        )
        editor = self._editor().create({"opening_slot_ids": self._rows((0, 9, 14))})
        row = editor.opening_slot_ids
        Editor = self.env["microsite.content.editor"].with_user(intruder)
        Row = self.env["microsite.content.editor.slot"].with_user(intruder)
        with self.assertRaises(AccessError):
            Editor.browse(editor.id).read(["microsite_intro_title"])
        with self.assertRaises(AccessError):
            Editor.browse(editor.id).write({"microsite_intro_title": "hacked"})
        with self.assertRaises(AccessError):
            Row.browse(row.id).write({"close_time": 23})
        with self.assertRaises(AccessError):
            Row.create({"editor_id": editor.id, "weekday": "1", "open_time": 1, "close_time": 2})
        editor.action_save()
        self.assertEqual(self.shop.microsite_opening_hours, "L 09:00-14:00")
        self.assertFalse(self.shop.microsite_intro_title)

    def test_bad_rows_are_refused_on_the_screen(self):
        with self.assertRaises(ValidationError):
            self._editor().create({"opening_slot_ids": self._rows((0, 14, 9))})
        with self.assertRaises(ValidationError):
            self._editor().create(
                {"opening_slot_ids": self._rows((0, 9, 14), (0, 13, 18))}
            )
        self.assertFalse(self.shop.microsite_opening_slot_ids)
