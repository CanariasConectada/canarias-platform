# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools.misc import format_datetime

from ..models.project_task import VISIT_OUTCOMES


class ProjectFieldVisitLog(models.TransientModel):
    """One visit of a consultant to a business, posted to the task chatter.

    Designed for the phone at the shop door: date and consultant come
    prefilled, the outcome is one tap, notes are plain text and the photos or
    signed documents are attached straight from the camera.
    """

    _name = "project.field.visit.log"
    _description = "Log a field visit"

    task_id = fields.Many2one("project.task", required=True, ondelete="cascade")
    project_id = fields.Many2one(related="task_id.project_id")
    business_name = fields.Char(related="task_id.business_name")
    visit_date = fields.Datetime(
        string="Visit date", required=True, default=fields.Datetime.now
    )
    user_id = fields.Many2one(
        "res.users",
        string="Consultant",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    outcome = fields.Selection(VISIT_OUTCOMES, required=True, default="visited")
    stage_id = fields.Many2one(
        "project.task.type",
        string="Move to stage",
        domain="[('project_ids', 'in', project_id)]",
        help="Leave empty to keep the task where it is.",
    )
    notes = fields.Text()
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "project_field_visit_log_attachment_rel",
        "wizard_id",
        "attachment_id",
        string="Evidence",
        help="Photos and documents taken during the visit.",
    )

    @api.model
    def _own_pending_attachments(self, attachments):
        """Attachments this user just uploaded through the wizard.

        Never re-home an attachment that already belongs to another record
        or to somebody else.
        """
        return attachments.sudo().filtered(
            lambda a: a.create_uid == self.env.user
            and (a.res_model in (self._name, False) or not a.res_id)
        )

    def _field_visit_message_values(self):
        self.ensure_one()
        outcome_labels = dict(self._fields["outcome"]._description_selection(self.env))
        return {
            "visit_date": format_datetime(
                self.env, self.visit_date, tz=self.env.user.tz, dt_format="short"
            ),
            "consultant": self.user_id.name,
            "outcome": outcome_labels.get(self.outcome, ""),
            "stage": self.stage_id.name,
            "notes": (self.notes or "").strip(),
        }

    def action_log_visit(self):
        self.ensure_one()
        task = self.task_id
        body = self.env["ir.qweb"]._render(
            "project_field_visit.field_visit_message",
            self._field_visit_message_values(),
        )
        attachments = self._own_pending_attachments(self.attachment_ids)
        attachments.write({"res_model": "project.task", "res_id": task.id})
        task.message_post(
            body=body,
            message_type="comment",
            subtype_xmlid="mail.mt_note",
            attachment_ids=attachments.ids,
        )
        vals = {
            "field_visit_last_date": self.visit_date,
            "field_visit_last_outcome": self.outcome,
        }
        if self.stage_id:
            vals["stage_id"] = self.stage_id.id
        task.write(vals)
        return {"type": "ir.actions.act_window_close"}
