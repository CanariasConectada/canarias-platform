# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class SilverPositiveItem(models.Model):
    _name = 'silver.positive.item'
    _description = 'Item positivo Silver Economy'
    _order = 'sequence, id'

    survey_id = fields.Many2one(
        'survey.survey',
        string='Encuesta',
        required=True,
        ondelete='cascade',
        index=True,
    )
    question_id = fields.Many2one(
        'survey.question',
        string='Pregunta',
        required=True,
        domain="[('survey_id', '=', survey_id), ('is_page', '=', False)]",
    )
    min_score = fields.Float(
        string='Score mínimo',
        default=0,
        help='Score mínimo que debe obtener el usuario en esta pregunta para que el item aparezca como positivo en el microsite',
    )
    label = fields.Char(
        string='Texto a mostrar',
        required=True,
        translate=True,
    )
    icon = fields.Char(
        string='Icono',
        default='fa-check-circle',
        help='Clase Font Awesome para el icono que acompaña el item en el microsite. Ej: fa-wheelchair, fa-heart, fa-universal-access',
    )
    sequence = fields.Integer(
        string='Secuencia',
        default=10,
    )

    @api.onchange('question_id')
    def _onchange_question_id(self):
        if self.question_id and not self.label:
            self.label = self.question_id.title
