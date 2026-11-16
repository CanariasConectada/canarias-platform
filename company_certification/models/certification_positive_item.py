# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models


class CertificationPositiveItem(models.Model):
    """DEPRECATED since 19.0.2.10.0: use ``certification.highlight``.

    Question-backed items used to live here, on the survey, while the curated
    icons lived on the certification type, and the microsite showed one list
    or the other. Both are now a single catalogue on the type
    (``certification.highlight`` with its trigger fields), and the
    19.0.2.10.0 migration turned every row of this model into a highlight.

    The model and its table are kept so no data is lost; nothing reads them
    any more and their backend UI is gone. ``migrated_highlight_id`` records
    where each row went and makes the migration idempotent.
    """

    _name = "certification.positive.item"
    _description = "Certification Positive Item (deprecated)"
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
    migrated_highlight_id = fields.Many2one(
        "certification.highlight",
        ondelete="set null",
        readonly=True,
        copy=False,
        help="Catalogue item this row was migrated into.",
    )

    @api.onchange("question_id")
    def _onchange_question_id(self):
        if self.question_id and not self.label:
            self.label = self.question_id.title
