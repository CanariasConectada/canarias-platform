# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FieldVisitCase

MANAGER = "project_field_visit.group_field_visit_manager"


@tagged("post_install", "-at_install")
class TestFieldVisitMicrositeStatus(FieldVisitCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.task = cls.env["project.task"].create(
            {
                "name": "Zzfv Bakery visit",
                "project_id": cls.project.id,
                "business_company_id": cls.business.id,
            }
        )

    def _patched(self, items, calls):
        def missing(companies):
            calls.append(companies)
            return {company.id: list(items) for company in companies}

        return patch.object(
            type(self.env["res.company"]), "_get_microsite_missing_items", missing
        )

    def _incomplete(self):
        return self.env["project.task"].search(
            [
                ("is_field_visit_project", "=", True),
                ("business_company_id", "!=", False),
                ("field_visit_microsite_complete", "=", False),
            ]
        )

    def test_status_on_link_and_cron(self):
        # Checked as soon as the task names its business.
        self.assertFalse(self.task.field_visit_microsite_complete)
        self.assertIn("Hero image", self.task.field_visit_microsite_missing)
        self.assertIn(self.task, self._incomplete())
        other = self.env["project.task"].create(
            {"name": "Zzfv prospect", "project_id": self.project.id}
        )
        self.assertFalse(other.field_visit_microsite_missing)
        # The merchant completes the microsite: the daily cron sees it, with
        # one batched check for every task.
        calls = []
        with self._patched([], calls):
            self.env["project.task"]._cron_field_visit_refresh_microsite_status()
        self.assertEqual(len(calls), 1)
        self.assertTrue(self.task.field_visit_microsite_complete)
        self.assertFalse(self.task.field_visit_microsite_missing)
        self.assertNotIn(self.task, self._incomplete())
        # Unlinked from the business: no status any more.
        self.task.write({"business_company_id": False, "business_partner_id": False})
        self.assertFalse(self.task.field_visit_microsite_complete)
        self.assertNotIn(self.task, self._incomplete())

    def test_refresh_action_for_managers_only(self):
        task = self.task.with_user(self.consultant)
        with self.assertRaises(AccessError):
            task.action_field_visit_refresh_microsite_status()
        self.consultant.group_ids = [(4, self.env.ref(MANAGER).id)]
        calls = []
        with self._patched(["Logo", "Phone"], calls):
            task.action_field_visit_refresh_microsite_status()
        self.assertEqual(self.task.field_visit_microsite_missing, "Logo\nPhone")
        action = self.env.ref(
            "project_field_visit.action_server_field_visit_microsite_status"
        )
        self.assertEqual(action.group_ids, self.env.ref(MANAGER))
