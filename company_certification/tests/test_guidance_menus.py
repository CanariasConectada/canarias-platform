# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Instructions and the online courses are reachable by a seal holder.

The instructions already lived on the questionnaire, but the only backend
screen showing them was the seal's configuration form, which is
manager-only. The courses live on the portal website; the Formación menu
links there through the seal's ``training_url``.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestGuidanceMenus(CertificationCase):
    MENUS = (
        "company_certification.menu_certification_instructions",
        "company_certification.menu_certification_training",
        "company_certification.menu_certification_training_silver",
        "company_certification.menu_certification_training_sustainability",
    )
    COURSES = (
        # (server action, shipped seal)
        (
            "company_certification.action_training_silver",
            "company_certification.certification_type_silver",
        ),
        (
            "company_certification.action_training_sustainability",
            "company_certification.certification_type_sustainability",
        ),
    )

    def _visible_menus(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_a_seal_holder_reaches_every_entry(self):
        visible = self._visible_menus(self.user)
        for xmlid in self.MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertIn(self.env.ref(xmlid).id, visible)

    def test_a_plain_internal_user_does_not(self):
        visible = self._visible_menus(self.plain_user)
        for xmlid in self.MENUS:
            with self.subTest(xmlid=xmlid):
                self.assertNotIn(self.env.ref(xmlid).id, visible)

    def test_the_training_menu_opens_the_seals_course_in_the_same_tab(self):
        """The link is data on the seal, resolved when the holder clicks."""
        for action_xmlid, seal_xmlid in self.COURSES:
            with self.subTest(action=action_xmlid):
                url = "https://example.test/course/%s" % seal_xmlid.rsplit("_", 1)[-1]
                self.env.ref(seal_xmlid).training_url = url
                result = self.env.ref(action_xmlid).with_user(self.user).run()
                self.assertEqual(result["type"], "ir.actions.act_url")
                self.assertEqual(result["url"], url)
                self.assertEqual(result["target"], "self")

    def test_the_training_menu_falls_back_to_the_course_catalogue(self):
        seal = self.env.ref("company_certification.certification_type_silver")
        seal.training_url = False
        action = self.env.ref("company_certification.action_training_silver")
        result = action.with_user(self.user).run()
        self.assertEqual(result["url"], "https://canariasconectada.es/slides")

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
