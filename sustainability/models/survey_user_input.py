# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class SurveyUserInput(models.Model):
    _inherit = 'survey.user_input'

    # Vinculación a empresa
    company_id = fields.Many2one(
        'res.company',
        string='Empresa evaluada',
        index=True,
        help='Empresa a la que corresponde esta evaluación'
    )
    
    # Campos de certificación
    certification_level = fields.Selection([
        ('none', 'Sin sello'),
        ('bronze', 'Bronce'),
        ('silver', 'Plata'),
        ('gold', 'Oro'),
    ], string='Nivel de certificación', compute='_compute_certification_level', store=True)
    
    # Control de plazos
    next_attempt_date = fields.Date(
        string='Próximo intento disponible',
        compute='_compute_next_attempt_date',
        store=True
    )
    expiry_date = fields.Date(
        string='Fecha de expiración del sello',
        compute='_compute_expiry_date',
        store=True
    )
    
    # Auditoría de ediciones admin
    is_manually_overridden = fields.Boolean(
        string='Puntuación editada manualmente',
        default=False,
        help='Indica si un administrador modificó la puntuación'
    )
    override_user_id = fields.Many2one(
        'res.users',
        string='Editado por',
        readonly=True
    )
    override_date = fields.Datetime(
        string='Fecha de edición',
        readonly=True
    )
    override_reason = fields.Text(
        string='Motivo de edición'
    )
    original_scoring_total = fields.Float(
        string='Puntuación original',
        readonly=True,
        digits=(10, 2)
    )

    # NOTE on the delegation pattern used below: the certification fields
    # (certification_level, next_attempt_date, expiry_date) and their
    # compute methods are also defined by other certification engines
    # inheriting survey.user_input (e.g. company_certification or
    # silver_economy). When those modules are co-installed, this class
    # shadows their compute methods for EVERY record, so records that do
    # not belong to a Sustainability survey are handed back to the
    # shadowed implementation with ``super(SurveyUserInput, other_inputs)``.
    # The super() call is inlined (not factored into a shared helper) on
    # purpose: a helper with the same name in several verticals would
    # always dispatch from the top of the MRO again and recurse forever.
    @api.depends('scoring_total', 'survey_id', 'is_manually_overridden')
    def _compute_certification_level(self):
        sustain_inputs = self.filtered(lambda ui: ui.survey_id.is_sustainability)
        other_inputs = self - sustain_inputs
        if other_inputs:
            parent = super(SurveyUserInput, other_inputs)
            if hasattr(parent, '_compute_certification_level'):
                parent._compute_certification_level()
            else:
                other_inputs.certification_level = 'none'
        for user_input in sustain_inputs:
            if user_input.survey_id.scoring_type == 'no_scoring':
                user_input.certification_level = 'none'
                continue

            survey = user_input.survey_id
            score = user_input.scoring_total
            max_score = survey.sustain_max_score or 80.0

            if max_score <= 0 or score < (survey.sustain_bronze_min or 40):
                user_input.certification_level = 'none'
            elif score <= (survey.sustain_silver_min or 55):
                user_input.certification_level = 'bronze'
            elif score <= (survey.sustain_gold_min or 70):
                user_input.certification_level = 'silver'
            else:
                user_input.certification_level = 'gold'

    @api.depends('create_date', 'certification_level', 'state', 'survey_id')
    def _compute_next_attempt_date(self):
        sustain_inputs = self.filtered(lambda ui: ui.survey_id.is_sustainability)
        other_inputs = self - sustain_inputs
        if other_inputs:
            parent = super(SurveyUserInput, other_inputs)
            if hasattr(parent, '_compute_next_attempt_date'):
                parent._compute_next_attempt_date()
            else:
                other_inputs.next_attempt_date = False
        for user_input in sustain_inputs:
            if user_input.state != 'done':
                user_input.next_attempt_date = False
                continue
            survey = user_input.survey_id
            cooldown = survey.sustain_cooldown_months or 3
            validity = survey.sustain_validity_years or 1
            if user_input.certification_level == 'none':
                user_input.next_attempt_date = fields.Date.from_string(
                    user_input.create_date) + relativedelta(months=cooldown)
            else:
                user_input.next_attempt_date = fields.Date.from_string(
                    user_input.create_date) + relativedelta(years=validity)

    @api.depends('create_date', 'certification_level', 'state', 'survey_id')
    def _compute_expiry_date(self):
        sustain_inputs = self.filtered(lambda ui: ui.survey_id.is_sustainability)
        other_inputs = self - sustain_inputs
        if other_inputs:
            parent = super(SurveyUserInput, other_inputs)
            if hasattr(parent, '_compute_expiry_date'):
                parent._compute_expiry_date()
            else:
                other_inputs.expiry_date = False
        for user_input in sustain_inputs:
            if user_input.state != 'done' or user_input.certification_level == 'none':
                user_input.expiry_date = False
            else:
                validity = user_input.survey_id.sustain_validity_years or 1
                user_input.expiry_date = fields.Date.from_string(
                    user_input.create_date) + relativedelta(years=validity)

    def action_override_score(self, new_score, reason=False):
        """Permite a un admin sobrescribir la puntuación con auditoría"""
        self.ensure_one()
        if not self.survey_id.is_sustainability:
            # Not a Sustainability evaluation: this method name is shared
            # with other certification engines, delegate when one exists.
            parent = super()
            if hasattr(parent, 'action_override_score'):
                return parent.action_override_score(new_score, reason=reason)
            # No other engine implements it either: refuse instead of
            # stamping Sustainability override fields on a foreign
            # evaluation (they share columns with company_certification
            # and would silently downgrade its computed level to 'none').
            raise UserError(_('Esta evaluación no pertenece a Sostenibilidad.'))
        if not self.env.user.has_group('sustainability.group_sustainability_manager'):
            raise UserError(_('Solo administradores pueden editar puntuaciones.'))
        
        if not self.is_manually_overridden:
            self.original_scoring_total = self.scoring_total
        
        self.write({
            'scoring_total': new_score,
            'is_manually_overridden': True,
            'override_user_id': self.env.user.id,
            'override_date': fields.Datetime.now(),
            'override_reason': reason,
        })
        self._compute_scoring_values()
        self._compute_certification_level()

    @api.model
    def action_start_new_sustainability_evaluation(self):
        """Acción para iniciar una nueva evaluación Sostenibilidad desde el backend"""
        user = self.env.user
        if not user.company_id:
            raise UserError(_('Debe tener una empresa asignada para realizar la evaluación.'))
        
        survey = self.env['survey.survey'].search([
            ('is_sustainability', '=', True),
            ('active', '=', True),
        ], limit=1)
        
        if not survey:
            raise UserError(_('No hay un cuestionario Sostenibilidad configurado. Contacte al administrador.'))
        
        return survey.action_start_sustainability_evaluation()

    def _mark_done(self):
        """Al completar la evaluación, enviar notificación de nuevo sello si aplica
        y forzar recomputación del nivel en la empresa para actualizar badges."""
        res = super()._mark_done()
        # Forzar que todos los campos compute de esta evaluación se calculen
        # antes de usarlos para actualizar la empresa
        self.env.flush_all()
        for user_input in self:
            if user_input.survey_id.is_sustainability and user_input.company_id:
                # Invalidar y recomputar certificación de la empresa
                user_input.company_id.invalidate_recordset(fnames=['sustain_certification_level', 'sustain_certification_date', 'sustain_expiry_date', 'sustain_cert_score'])
                user_input.company_id._compute_sustain_certification()
                user_input.company_id._compute_sustain_cert_details()
                user_input.company_id.flush_recordset()
                if user_input.certification_level != 'none':
                    user_input._send_new_badge_notification()
        return res

    def write(self, vals):
        """Al modificar una evaluación, recalcular certificación de la empresa."""
        res = super().write(vals)
        if any(f in vals for f in ['certification_level', 'state', 'expiry_date', 'survey_id', 'company_id', 'test_entry']):
            for record in self.filtered(lambda r: r.survey_id.is_sustainability and r.company_id):
                record.company_id._compute_sustain_certification()
                record.company_id._compute_sustain_cert_details()
                record.company_id.flush_recordset()
        return res

    def unlink(self):
        """Al eliminar una evaluación, recalcular certificación de la empresa."""
        companies = self.filtered(lambda r: r.survey_id.is_sustainability).mapped('company_id')
        res = super().unlink()
        for company in companies:
            company._compute_sustain_certification()
            company._compute_sustain_cert_details()
            company.flush_recordset()
        return res

    @api.model
    def _cron_sustainability_retry_reminder(self):
        """Envía recordatorio a usuarios que ya pueden reintentar (cooldown 3 meses cumplido)"""
        today = fields.Date.today()
        evaluations = self.search([
            ('survey_id.is_sustainability', '=', True),
            ('certification_level', '=', 'none'),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
            ('next_attempt_date', '<=', today),
            ('create_date', '>=', fields.Datetime.to_datetime('2026-01-01')),  # Solo evaluaciones recientes
        ])
        template = self.env.ref('sustainability.mail_template_sustainability_retry_available', raise_if_not_found=False)
        if template:
            for evaluation in evaluations:
                if evaluation.partner_id.email:
                    try:
                        # No force_send: queue in mail.mail so the core mail
                        # queue handles delivery and retries.
                        template.send_mail(evaluation.id)
                    except Exception:
                        # Poison-record isolation: one failing evaluation must
                        # not abort the reminders for the rest of the queue.
                        _logger.exception(
                            "Sustainability retry reminder failed for "
                            "evaluation %s (company %s)",
                            evaluation.id,
                            evaluation.company_id.id,
                        )
                        continue

    @api.model
    def _cron_sustainability_renewal_reminder(self):
        """Envía recordatorio de renovación N días antes de la expiración"""
        today = fields.Date.today()
        # Usar el máximo de días configurado entre todos los surveys (fallback 30)
        surveys = self.env['survey.survey'].search([('is_sustainability', '=', True)])
        max_days = max(surveys.mapped('sustain_renewal_reminder_days') or [30])
        reminder_date = today + timedelta(days=max_days)
        evaluations = self.search([
            ('survey_id.is_sustainability', '=', True),
            ('certification_level', '!=', 'none'),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
            ('expiry_date', '<=', reminder_date),
            ('expiry_date', '>=', today),
        ])
        template = self.env.ref('sustainability.mail_template_sustainability_renewal_due', raise_if_not_found=False)
        if template:
            for evaluation in evaluations:
                if evaluation.partner_id.email:
                    try:
                        # No force_send: queue in mail.mail so the core mail
                        # queue handles delivery and retries.
                        template.send_mail(evaluation.id)
                    except Exception:
                        # Poison-record isolation: one failing evaluation must
                        # not abort the reminders for the rest of the queue.
                        _logger.exception(
                            "Sustainability renewal reminder failed for "
                            "evaluation %s (company %s)",
                            evaluation.id,
                            evaluation.company_id.id,
                        )
                        continue

    @api.model
    def _cron_sustainability_expiry_alert(self):
        """Alerta al admin cuando un sello ha expirado"""
        today = fields.Date.today()
        evaluations = self.search([
            ('survey_id.is_sustainability', '=', True),
            ('certification_level', '!=', 'none'),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
            ('expiry_date', '<', today),
        ])
        template = self.env.ref('sustainability.mail_template_sust_admin_expiry_alert', raise_if_not_found=False)
        if template:
            for evaluation in evaluations:
                if evaluation.survey_id.user_id.email:
                    try:
                        # No force_send: queue in mail.mail so the core mail
                        # queue handles delivery and retries.
                        template.send_mail(evaluation.id)
                    except Exception:
                        # Poison-record isolation: one failing evaluation must
                        # not abort the alerts for the rest of the queue.
                        _logger.exception(
                            "Sustainability expiry alert failed for "
                            "evaluation %s (company %s)",
                            evaluation.id,
                            evaluation.company_id.id,
                        )
                        continue

    def _send_new_badge_notification(self):
        """Envía notificación de nuevo sello obtenido al completar evaluación"""
        self.ensure_one()
        if not self.survey_id.is_sustainability:
            # Not a Sustainability evaluation: let the shadowed engine
            # (e.g. company_certification) send its own notification.
            parent = super()
            if hasattr(parent, '_send_new_badge_notification'):
                return parent._send_new_badge_notification()
            return
        if self.certification_level == 'none':
            return
        template = self.env.ref('sustainability.mail_template_sust_new_badge', raise_if_not_found=False)
        if template and self.partner_id.email:
            template.send_mail(self.id, force_send=True)

    def action_continue_sustainability_evaluation(self):
        """Redirige al usuario para continuar una evaluación en curso (new/in_progress).
        
        Se usa desde el botón 'Continuar' en la vista list de Mis Evaluaciones.
        """
        self.ensure_one()
        if self.state not in ('new', 'in_progress'):
            raise UserError(_('Esta evaluación ya ha sido completada.'))
        if not self.survey_id:
            raise UserError(_('No se encontró la encuesta asociada.'))
        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '/survey/start/%s?answer_token=%s' % (self.survey_id.access_token, self.access_token),
        }

    def action_start_sustainability_from_form(self):
        """Inicia una evaluación Sostenibilidad desde el formulario de creación.
        
        Este método se llama desde el botón en la vista form cuando el usuario
        hace clic en 'Nuevo' desde 'Mis Evaluaciones'. Valida cooldown,
        crea la evaluación y redirige a la encuesta.
        """
        self.ensure_one()
        user = self.env.user
        if not user.company_id:
            raise UserError(_('Debe tener una empresa asignada para realizar la evaluación.'))

        survey = self.env['survey.survey'].search([
            ('is_sustainability', '=', True),
            ('active', '=', True),
        ], limit=1)
        if not survey:
            raise UserError(_('No hay un cuestionario Sostenibilidad configurado. Contacte al administrador.'))

        # Validar cooldown por EMPRESA (cualquier usuario de la misma empresa)
        last_attempt = self.env['survey.user_input'].search([
            ('survey_id', '=', survey.id),
            ('company_id', '=', user.company_id.id),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
        ], order='create_date desc', limit=1)
        if last_attempt and last_attempt.next_attempt_date and last_attempt.next_attempt_date > fields.Date.today():
            raise UserError(_('No puede realizar una nueva evaluación hasta el %s.') % last_attempt.next_attempt_date)

        # Crear evaluación real con company_id incluido para cumplir ir.rule
        answer = self.env['survey.user_input'].create({
            'survey_id': survey.id,
            'company_id': user.company_id.id,
            'partner_id': user.partner_id.id,
            'test_entry': False,
        })

        return {
            'type': 'ir.actions.act_url',
            'target': 'new',
            'url': '/survey/start/%s?answer_token=%s' % (survey.access_token, answer.access_token),
        }

    def action_reset_override(self):
        """Restaura la puntuación original"""
        self.ensure_one()
        if not self.survey_id.is_sustainability:
            # Not a Sustainability evaluation: this method name is shared
            # with other certification engines, delegate when one exists.
            parent = super()
            if hasattr(parent, 'action_reset_override'):
                return parent.action_reset_override()
        if not self.env.user.has_group('sustainability.group_sustainability_manager'):
            raise UserError(_('Solo administradores pueden revertir ediciones.'))
        
        if not self.is_manually_overridden:
            return
        
        self.write({
            'scoring_total': self.original_scoring_total,
            'is_manually_overridden': False,
            'override_user_id': False,
            'override_date': False,
            'override_reason': False,
        })
        self._compute_scoring_values()
        self._compute_certification_level()
