# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError


class SilverEconomyController(http.Controller):

    def _get_active_silver_survey(self):
        """Busca la encuesta Silver Economy activa."""
        return request.env['survey.survey'].sudo().search([
            ('is_silver_economy', '=', True),
            ('active', '=', True),
        ], limit=1)

    def _check_silver_cooldown(self, survey, user):
        """Verifica cooldown y devuelve el último intento o None."""
        return request.env['survey.user_input'].sudo().search([
            ('survey_id', '=', survey.id),
            ('company_id', '=', user.company_id.id),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
        ], order='create_date desc', limit=1)

    def _create_silver_answer(self, survey, user):
        """Crea la respuesta con company_id incluido."""
        return request.env['survey.user_input'].sudo().create({
            'survey_id': survey.id,
            'partner_id': user.partner_id.id,
            'company_id': user.company_id.id,
            'test_entry': False,
        })

    def _handle_silver_start(self, survey):
        """Lógica común de inicio de evaluación."""
        user = request.env.user
        if not user.company_id:
            return request.render('silver_economy.silver_no_company', {})

        last_attempt = self._check_silver_cooldown(survey, user)
        if last_attempt and last_attempt.next_attempt_date and last_attempt.next_attempt_date > fields.Date.today():
            return request.render('silver_economy.silver_cooldown', {
                'next_date': last_attempt.next_attempt_date,
                'survey': survey,
            })

        try:
            answer = self._create_silver_answer(survey, user)
        except UserError as e:
            return request.render('silver_economy.silver_error', {'error': str(e)})

        return request.redirect('/survey/start/%s?answer_token=%s' % (survey.access_token, answer.access_token))

    @http.route('/silver_economy/start', type='http', auth='user', website=True)
    def silver_start_generic(self, **kwargs):
        """Ruta genérica para iniciar evaluación Silver (sin token)."""
        survey = self._get_active_silver_survey()
        if not survey:
            return request.render('silver_economy.silver_error', {
                'error': 'No hay ningún cuestionario Silver Economy activo. Contacte con el administrador.'
            })
        return self._handle_silver_start(survey)

    @http.route('/silver_economy/start/<string:survey_token>', type='http', auth='user', website=True)
    def silver_start(self, survey_token, **kwargs):
        """Ruta para que usuarios internos inicien una evaluación Silver Economy real"""
        survey = request.env['survey.survey'].sudo().search([
            ('access_token', '=', survey_token),
            ('is_silver_economy', '=', True),
            ('active', '=', True),
        ], limit=1)
        if not survey:
            return request.render('silver_economy.silver_error', {
                'error': 'Cuestionario no encontrado o inactivo.'
            })
        return self._handle_silver_start(survey)

    @http.route('/silver_economy/close', type='http', auth='user', website=True)
    def silver_close(self, **kwargs):
        """Redirige de vuelta a Mis Evaluaciones en el backend.

        Se usa desde el botón 'Cerrar' en la página de finalización del survey
        para evitar que Odoo 19 frontend reescriba mal la URL /web#action=...
        """
        return request.redirect('/web#action=silver_economy.action_silver_evaluations')

    @http.route('/silver-economy', type='http', auth='public', website=True)
    def silver_economy_page(self, **kwargs):
        """Página pública de información sobre Silver Economy (Formaciones)."""
        survey = self._get_active_silver_survey()
        return request.render('silver_economy.silver_economy_page', {
            'survey': survey,
        })

    @http.route('/silver-economy/instructions', type='http', auth='public', website=True)
    def silver_instructions_page(self, **kwargs):
        """Página pública con las instrucciones del examen Silver Economy."""
        survey = self._get_active_silver_survey()
        return request.render('silver_economy.silver_instructions_page', {
            'survey': survey,
        })
