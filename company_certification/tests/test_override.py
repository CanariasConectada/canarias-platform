# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestManualOverride(CertificationCase):
    def test_manager_override_and_reset(self):
        answer = self._run_evaluation(0)  # computed level: none
        answer.with_user(self.manager).action_override_level(
            "silver", reason="Verified on site"
        )
        self.assertEqual(answer.certification_level, "silver")
        self.assertTrue(answer.is_manually_overridden)
        self.assertEqual(answer.override_user_id, self.manager)
        self.assertEqual(answer.override_reason, "Verified on site")
        # The override also feeds the company status.
        self.assertEqual(self.company.certification_ids.level, "silver")
        # Reset restores the computed level and clears the audit trail.
        answer.with_user(self.manager).action_reset_override()
        self.assertEqual(answer.certification_level, "none")
        self.assertFalse(answer.is_manually_overridden)
        self.assertFalse(answer.override_user_id)
        self.assertFalse(self.company.certification_ids)

    def test_plain_member_cannot_override(self):
        answer = self._run_evaluation(0)
        with self.assertRaises(UserError):
            answer.with_user(self.user).action_override_level("gold")

    def test_form_edit_stamps_audit_trail(self):
        """Editing the manual fields from the form stamps user and date."""
        answer = self._run_evaluation(0)
        answer.with_user(self.manager).write(
            {"is_manually_overridden": True, "manual_certification_level": "bronze"}
        )
        self.assertEqual(answer.certification_level, "bronze")
        self.assertEqual(answer.override_user_id, self.manager)
        self.assertTrue(answer.override_date)
