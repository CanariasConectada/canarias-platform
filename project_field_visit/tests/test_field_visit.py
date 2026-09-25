# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import FieldVisitCase


@tagged("post_install", "-at_install")
class TestFieldVisit(FieldVisitCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.task = cls.env["project.task"].create(
            {
                "name": "Zzfv Bakery Demo",
                "project_id": cls.project.id,
                "business_company_id": cls.business.id,
            }
        )

    def test_phase_properties_created(self):
        names = [p["name"] for p in self.project.task_properties_definition]
        self.assertEqual(
            names,
            [
                "annex_number",
                "microsite",
                "justified_list",
                "graphic_evidence",
                "commitment_signed",
                "participation_status",
                "training",
                "declaration_signed",
            ],
        )
        # A project that already has its own fields keeps them.
        own = [{"name": "visit_score", "string": "Score", "type": "integer"}]
        other = self.env["project.project"].create(
            {"name": "Zzfv phase II", "is_field_visit_project": True}
        )
        other.task_properties_definition = own
        other._field_visit_ensure_properties()
        self.assertEqual(
            [p["name"] for p in other.task_properties_definition], ["visit_score"]
        )

    def test_business_fields_follow_the_company(self):
        website = self.env["website"].search([("company_id", "=", self.business.id)])
        self.assertEqual(self.task.business_partner_id, self.business.partner_id)
        self.assertEqual(self.task.business_website_id, website[:1])
        self.assertEqual(self.task.business_name, "Zzfv Bakery Demo")
        self.assertEqual(
            self.task.business_microsite_url, "https://zzfv-bakery-demo.example.com"
        )
        action = self.task.action_open_business_microsite()
        self.assertEqual(action["url"], "https://zzfv-bakery-demo.example.com")
        # Renaming the business keeps the stored name in sync.
        self.business.name = "Zzfv Bakery Renamed"
        self.assertEqual(self.task.business_name, "Zzfv Bakery Renamed")

    def test_consultant_reads_task_of_foreign_business(self):
        self.assertNotIn(self.business, self.consultant.company_ids)
        with self.assertRaises(AccessError):
            self.business.with_user(self.consultant).check_access("read")
        task = self.task.with_user(self.consultant)
        values = task.web_read(
            {
                "business_name": {},
                "business_microsite_url": {},
                "task_properties": {},
                "business_company_id": {"fields": {"display_name": {}}},
                "business_partner_id": {"fields": {"display_name": {}}},
                "business_website_id": {"fields": {"display_name": {}}},
            }
        )[0]
        self.assertEqual(values["business_name"], "Zzfv Bakery Demo")
        self.assertEqual(
            values["business_company_id"]["display_name"], "Zzfv Bakery Demo"
        )
        # The kanban and list views load without touching the business.
        task.web_search_read(
            [("id", "=", self.task.id)],
            {"business_name": {}, "business_microsite_url": {}, "stage_id": {}},
        )

    def _upload(self, user, name="shopfront.jpg"):
        return (
            self.env["ir.attachment"]
            .with_user(user)
            .create(
                {
                    "name": name,
                    "datas": base64.b64encode(b"fake image"),
                    "res_model": "project.field.visit.log",
                    "res_id": 0,
                }
            )
        )

    def test_consultant_logs_visit_with_evidence(self):
        photo = self._upload(self.consultant)
        wizard = (
            self.env["project.field.visit.log"]
            .with_user(self.consultant)
            .create(
                {
                    "task_id": self.task.id,
                    "outcome": "documents",
                    "notes": "Signed the commitment <b>today</b>",
                    "stage_id": self.stage.id,
                    "attachment_ids": [(6, 0, photo.ids)],
                }
            )
        )
        self.assertEqual(wizard.user_id, self.consultant)
        wizard.action_log_visit()
        message = self.task.message_ids.filtered(lambda m: m.attachment_ids == photo)
        self.assertEqual(len(message), 1)
        self.assertEqual(message.author_id, self.consultant.partner_id)
        self.assertIn("Zzfv Consultant", message.body)
        self.assertIn("Signed the commitment &lt;b&gt;today&lt;/b&gt;", message.body)
        self.assertEqual(
            (photo.res_model, photo.res_id), ("project.task", self.task.id)
        )
        self.assertEqual(self.task.stage_id, self.stage)
        self.assertEqual(self.task.field_visit_last_outcome, "documents")
        self.assertTrue(self.task.field_visit_last_date)

    def test_visit_never_steals_foreign_attachments(self):
        other = self.env["ir.attachment"].create(
            {
                "name": "contract.pdf",
                "datas": base64.b64encode(b"%PDF"),
                "res_model": "res.partner",
                "res_id": self.env.user.partner_id.id,
            }
        )
        wizard = self.env["project.field.visit.log"].create(
            {"task_id": self.task.id, "attachment_ids": [(6, 0, other.ids)]}
        )
        wizard.action_log_visit()
        self.assertEqual(other.res_model, "res.partner")

    def test_smart_buttons(self):
        self.assertEqual(self.business.field_visit_task_count, 1)
        self.assertEqual(self.business.partner_id.field_visit_task_count, 1)
        action = self.business.action_view_field_visits()
        tasks = self.env["project.task"].search(action["domain"])
        self.assertEqual(tasks, self.task)
        partner_action = self.business.partner_id.action_view_field_visits()
        self.assertEqual(
            self.env["project.task"].search(partner_action["domain"]), self.task
        )
        # Somebody outside the project app sees no counter and no error.
        merchant = self.env["res.users"].create(
            {
                "name": "Zzfv Merchant",
                "login": "zzfv_merchant",
                "company_id": self.owner.id,
                "company_ids": [(6, 0, self.owner.ids)],
                "group_ids": [(6, 0, [self.env.ref("base.group_user").id])],
            }
        )
        self.assertEqual(self.owner.with_user(merchant).field_visit_task_count, 0)

    def test_task_action_opens_visit_dialog(self):
        action = self.task.action_log_field_visit()
        self.assertEqual(action["res_model"], "project.field.visit.log")
        self.assertEqual(action["context"]["default_task_id"], self.task.id)
