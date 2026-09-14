# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Instructions and training material are readable by a seal holder.

Both already lived in the database -- the instructions on the questionnaire,
the material on the seal -- but the only backend screen showing either was
the seal's configuration form, which is manager-only.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestGuidanceMenus(CertificationCase):
    MENUS = (
        "company_certification.menu_certification_instructions",
        "company_certification.menu_certification_material",
    )

    def _visible_menus(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_a_seal_holder_reaches_both_entries(self):
        visible = self._visible_menus(self.user)
        for xmlid in self.MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self.env.ref(xmlid).id, visible)

    def test_a_plain_internal_user_does_not(self):
        visible = self._visible_menus(self.plain_user)
        for xmlid in self.MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, visible)

    def test_the_holder_reads_the_questionnaires_own_guidance(self):
        self.survey.write(
            {
                "description": "<p>Cómo se evalúa</p>",
                "description_done": "<p>Y cómo termina</p>",
            }
        )
        as_holder = self.cert_type.with_user(self.user)
        self.assertEqual(as_holder.instructions_html, "<p>Cómo se evalúa</p>")
        self.assertEqual(as_holder.closing_html, "<p>Y cómo termina</p>")

    def test_the_reading_room_stays_read_only(self):
        """The seal is configured from its own form, never from here."""
        with self.assertRaises(AccessError):
            self.cert_type.with_user(self.user).write({"name": "Renamed"})
