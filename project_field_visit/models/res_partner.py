# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from .project_task import CONSULTANT_GROUP


class ResPartner(models.Model):
    _inherit = "res.partner"

    # A contact the importer created for a business that is not on the
    # platform yet. Only those can be the business contact of a task without
    # a business company (see project.task._check_business_partner).
    is_field_visit_prospect = fields.Boolean(
        string="Field visit prospect", copy=False, groups=CONSULTANT_GROUP
    )
    # Stable identity for re-imports: the normalized name the prospect was
    # created with, and its grant annex number. Renaming the contact keeps it.
    field_visit_prospect_key = fields.Char(
        copy=False, index="btree_not_null", groups=CONSULTANT_GROUP
    )
    field_visit_annex_number = fields.Integer(
        string="Annex number", copy=False, groups=CONSULTANT_GROUP
    )
    field_visit_task_count = fields.Integer(
        compute="_compute_field_visit_task_count",
        string="Field visits",
        groups=CONSULTANT_GROUP,
    )

    @api.depends_context("uid")
    def _compute_field_visit_task_count(self):
        # The form is shared with people outside the programme (merchants
        # editing their company): they get no count rather than an error.
        if not self.env.user.has_group(CONSULTANT_GROUP):
            self.field_visit_task_count = 0
            return
        counts = dict(
            self.env["project.task"]._read_group(
                [
                    ("business_partner_id", "in", self.ids),
                    ("is_field_visit_project", "=", True),
                ],
                ["business_partner_id"],
                ["__count"],
            )
        )
        for partner in self:
            partner.field_visit_task_count = counts.get(partner, 0)

    def action_view_field_visits(self):
        self.ensure_one()
        return self.env["project.task"]._field_visit_action(
            [("business_partner_id", "=", self.id)],
            {"default_business_partner_id": self.id},
        )
