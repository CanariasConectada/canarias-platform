# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    field_visit_task_count = fields.Integer(
        compute="_compute_field_visit_task_count", string="Field visits"
    )

    def _compute_field_visit_task_count(self):
        # The form is shared with people outside the project app (merchants
        # editing their company): they get no count rather than an error.
        if not self.env.user.has_group("project.group_project_user"):
            self.field_visit_task_count = 0
            return
        counts = dict(
            self.env["project.task"]._read_group(
                [
                    ("business_company_id", "in", self.ids),
                    ("project_id.is_field_visit_project", "=", True),
                ],
                ["business_company_id"],
                ["__count"],
            )
        )
        for company in self:
            company.field_visit_task_count = counts.get(company, 0)

    def action_view_field_visits(self):
        self.ensure_one()
        return self.env["project.task"]._field_visit_action(
            [("business_company_id", "=", self.id)],
            {"default_business_company_id": self.id},
        )
