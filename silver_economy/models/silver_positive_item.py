# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class SilverPositiveItem(models.Model):
    _name = "silver.positive.item"
    _description = "Silver Economy Positive Item"
    _order = "sequence, id"

    survey_id = fields.Many2one(
        "survey.survey",
        string="Survey",
        required=True,
        ondelete="cascade",
        index=True,
    )
    question_id = fields.Many2one(
        "survey.question",
        string="Question",
        required=True,
        domain="[('survey_id', '=', survey_id), ('is_page', '=', False)]",
    )
    min_score = fields.Float(
        string="Minimum Score",
        default=0,
        help="Minimum score the answer must reach for the item to show up "
        "as positive on the microsite",
    )
    label = fields.Char(
        string="Display Text",
        required=True,
        translate=True,
    )
    icon = fields.Char(
        string="Icon",
        default="fa-check-circle",
        help="Font Awesome class for the icon shown next to the item on the "
        "microsite, e.g. fa-wheelchair, fa-heart, fa-universal-access",
    )
    sequence = fields.Integer(
        string="Sequence",
        default=10,
    )

    @api.onchange("question_id")
    def _onchange_question_id(self):
        if self.question_id and not self.label:
            self.label = self.question_id.title
