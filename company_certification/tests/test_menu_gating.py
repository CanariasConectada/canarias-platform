# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Visibility is gated by each vertical's user group.

A plain internal user (no vertical group) must not see the vertical's root
menu, its questionnaire or its evaluations. A user in the group sees only
their own vertical.
"""
from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestMenuGating(CertificationCase):
    def _visible_menus(self, user):
        return self.env["ir.ui.menu"].with_user(user)._visible_menu_ids()

    def test_menu_hidden_for_plain_internal_user(self):
        self.assertNotIn(
            self.cert_type.menu_id.id, self._visible_menus(self.plain_user)
        )

    def test_menu_visible_for_group_member(self):
        self.assertIn(self.cert_type.menu_id.id, self._visible_menus(self.user))

    def test_seeded_verticals_hidden_for_plain_internal_user(self):
        visible = self._visible_menus(self.plain_user)
        for xmlid in (
            "company_certification.certification_type_silver",
            "company_certification.certification_type_sustainability",
        ):
            cert_type = self.env.ref(xmlid)
            self.assertNotIn(cert_type.menu_id.id, visible)

    def test_config_menu_hidden_for_plain_internal_user(self):
        menu = self.env.ref("company_certification.menu_certification_root")
        self.assertNotIn(menu.id, self._visible_menus(self.plain_user))
        self.assertIn(menu.id, self._visible_menus(self.manager))

    def test_survey_read_gated_by_group(self):
        with self.assertRaises(AccessError):
            self.survey.with_user(self.plain_user).read(["title"])
        self.assertTrue(self.survey.with_user(self.user).read(["title"]))

    def test_survey_of_other_vertical_not_readable(self):
        """Group members only read the questionnaires of their vertical."""
        silver_survey = self.env.ref("company_certification.survey_silver_economy")
        with self.assertRaises(AccessError):
            silver_survey.with_user(self.user).read(["title"])

    def test_user_input_isolated_by_company_and_vertical(self):
        answer = self._run_evaluation(3)
        # The evaluating user sees their company's evaluation.
        self.assertIn(
            answer.id,
            self.env["survey.user_input"]
            .with_user(self.user)
            .search([("certification_type_id", "=", self.cert_type.id)])
            .ids,
        )
        # A group member of another company sees nothing.
        other_company = self.env["res.company"].create({"name": "Other Shop"})
        other_user = self.user.copy(
            {"login": "cert_other", "company_ids": [(6, 0, other_company.ids)]}
        )
        other_user.company_id = other_company
        self.assertFalse(
            self.env["survey.user_input"]
            .with_user(other_user)
            .search([("certification_type_id", "=", self.cert_type.id)])
        )
        # A plain internal user cannot read it at all.
        with self.assertRaises(AccessError):
            answer.with_user(self.plain_user).read(["state"])

    def test_manager_sees_all_evaluations_of_managed_vertical(self):
        answer = self._run_evaluation(3)
        found = (
            self.env["survey.user_input"]
            .with_user(self.manager)
            .search([("certification_type_id", "=", self.cert_type.id)])
        )
        self.assertIn(answer.id, found.ids)
