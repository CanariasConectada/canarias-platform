# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    certification_ids = fields.One2many(
        "res.company.certification",
        "company_id",
        string="Certifications",
    )
    certification_evaluation_count = fields.Integer(
        compute="_compute_certification_evaluation_count"
    )

    def _compute_certification_evaluation_count(self):
        for company in self:
            company.certification_evaluation_count = self.env[
                "survey.user_input"
            ].search_count(
                [
                    ("certification_type_id", "!=", False),
                    ("company_id", "=", company.id),
                    ("test_entry", "=", False),
                ]
            )

    def action_open_certification_evaluations(self):
        self.ensure_one()
        return {
            "name": _("Certification Evaluations - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "survey.user_input",
            "view_mode": "list,form",
            "domain": [
                ("certification_type_id", "!=", False),
                ("company_id", "=", self.id),
                ("test_entry", "=", False),
            ],
            "context": {"create": False},
        }

    def _get_valid_certifications(self):
        """Certification status records currently in force for the company.

        Uses sudo because it is called from public website rendering.
        """
        self.ensure_one()
        return self.sudo().certification_ids.filtered(lambda c: c._is_valid())

    def _get_certification_positive_items(self, cert_type):
        """Positive highlights of the last awarding evaluation.

        Returns a list of ``{'label': str, 'icon': str}`` dicts for the
        microsite QWeb template. Sudo: rendered in public website context.
        """
        self.ensure_one()
        status = self.sudo().certification_ids.filtered(
            lambda c: c.type_id == cert_type and c._is_valid()
        )
        awarding = status.user_input_id
        if not awarding or not awarding.survey_id.positive_item_ids:
            return []
        lines = awarding.user_input_line_ids
        items = []
        for item in awarding.survey_id.positive_item_ids.sorted("sequence"):
            line = lines.filtered(lambda ln: ln.question_id == item.question_id)
            if line and max(line.mapped("answer_score")) >= item.min_score:
                items.append(
                    {"label": item.label, "icon": item.icon or "fa-check-circle"}
                )
        return items
