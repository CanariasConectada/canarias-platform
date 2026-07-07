# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class CertificationPositiveItem(models.Model):
    """Question-backed highlight shown on the company microsite.

    When the last valid evaluation scored at least ``min_score`` on
    ``question_id``, the item's label is displayed in the certification
    section of the company microsite.
    """

    _name = "certification.positive.item"
    _description = "Certification Positive Item"
    _order = "sequence, id"

    survey_id = fields.Many2one(
        "survey.survey",
        required=True,
        ondelete="cascade",
        index=True,
    )
    question_id = fields.Many2one(
        "survey.question",
        required=True,
        domain="[('survey_id', '=', survey_id), ('is_page', '=', False)]",
    )
    min_score = fields.Float(
        default=0,
        help="Minimum score on the question for the item to show up as a "
        "positive highlight on the microsite.",
    )
    label = fields.Char(required=True, translate=True)
    icon = fields.Char(
        default="fa-check-circle",
        help="Font Awesome class shown next to the item, e.g. fa-wheelchair.",
    )
    sequence = fields.Integer(default=10)

    @api.onchange("question_id")
    def _onchange_question_id(self):
        if self.question_id and not self.label:
            self.label = self.question_id.title
