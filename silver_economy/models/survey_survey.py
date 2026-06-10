# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class SurveySurvey(models.Model):
    _inherit = 'survey.survey'

    is_silver_economy = fields.Boolean(
        string='Es evaluación Silver Economy',
        default=False,
        help='Si está marcado, esta encuesta se usa para certificación Silver Economy'
    )
    
    # Umbrales configurables de puntuación
    silver_max_score = fields.Float(
        string='Puntuación máxima',
        default=80.0,
        help='Puntuación máxima posible (40 preguntas x 2 puntos)'
    )
    silver_bronze_min = fields.Float(
        string='Mínimo Bronce',
        default=40.0,
        help='Puntuación mínima para obtener sello Bronce'
    )
    silver_silver_min = fields.Float(
        string='Mínimo Plata',
        default=56.0,
        help='Puntuación mínima para obtener sello Plata'
    )
    silver_gold_min = fields.Float(
        string='Mínimo Oro',
        default=71.0,
        help='Puntuación mínima para obtener sello Oro'
    )

    # Tiempos configurables
    silver_cooldown_months = fields.Integer(
        string='Meses de espera tras reprobar',
        default=3,
        help='Número de meses que debe esperar el usuario para reintentar si no aprueba'
    )
    silver_validity_years = fields.Integer(
        string='Años de validez del sello',
        default=1,
        help='Número de años que el sello permanece válido tras obtenerlo'
    )
    silver_renewal_reminder_days = fields.Integer(
        string='Días de aviso previo a renovación',
        default=30,
        help='Días antes de la expiración para enviar recordatorio de renovación'
    )

    positive_item_ids = fields.One2many(
        'silver.positive.item',
        'survey_id',
        string='Items positivos',
        help='Items que aparecerán en el microsite cuando el usuario responda correctamente la pregunta asociada',
    )

    def action_start_silver_evaluation(self):
        """Acción para usuarios internos: inicia una evaluación real (no test)"""
        self.ensure_one()
        if not self.is_silver_economy:
            raise UserError(_('Esta encuesta no está configurada como evaluación Silver Economy.'))
        
        user = self.env.user
        if not user.company_id:
            raise UserError(_('Debe tener una empresa asignada para realizar la evaluación.'))
        
        # Verificar cooldown
        last_attempt = self.env['survey.user_input'].search([
            ('survey_id', '=', self.id),
            ('company_id', '=', user.company_id.id),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
        ], order='create_date desc', limit=1)
        
        if last_attempt and last_attempt.next_attempt_date and last_attempt.next_attempt_date > fields.Date.today():
            raise UserError(_('No puede realizar una nueva evaluación hasta el %s.') % last_attempt.next_attempt_date)
        
        # Crear respuesta real (no test) con company_id incluido para cumplir ir.rule
        answer = self.env['survey.user_input'].create({
            'survey_id': self.id,
            'partner_id': user.partner_id.id,
            'company_id': user.company_id.id,
            'test_entry': False,
        })
        
        return {
            'type': 'ir.actions.act_url',
            'name': _('Iniciar evaluación Silver Economy'),
            'target': 'new',
            'url': '/survey/start/%s?answer_token=%s' % (self.access_token, answer.access_token),
        }
