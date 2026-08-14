# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    certification_type_id = fields.Many2one(
        "certification.type",
        string="Certification Type",
        index=True,
        help="When set, this survey is the questionnaire of a company "
        "certification vertical.",
    )
    positive_item_ids = fields.One2many(
        "certification.positive.item",
        "survey_id",
        string="Positive Items",
        help="Items displayed on the company microsite when the related "
        "question was answered above its minimum score.",
    )
