# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    sustain_certification_level = fields.Selection([
        ('none', 'Sin sello'),
        ('bronze', 'Bronce'),
        ('silver', 'Plata'),
        ('gold', 'Oro'),
    ], string='Nivel Sostenibilidad', compute='_compute_sustain_certification', store=True)
    
    sustain_certification_date = fields.Date(
        string='Fecha de certificación Sostenibilidad',
        compute='_compute_sustain_certification',
        store=True
    )
    
    sustain_expiry_date = fields.Date(
        string='Expiración sello Sostenibilidad',
        compute='_compute_sustain_certification',
        store=True
    )
    
    sustain_evaluation_count = fields.Integer(
        string='Evaluaciones Sostenibilidad',
        compute='_compute_sustain_evaluation_count'
    )
    
    sustain_cert_score = fields.Float(
        string='Puntuación Sostenibilidad (%)',
        compute='_compute_sustain_cert_details',
        store=True
    )
    
    def action_open_sustainability_evaluations(self):
        """Abre el listado de evaluaciones Sostenibilidad de esta empresa"""
        self.ensure_one()
        return {
            'name': _('Evaluaciones Sostenibilidad - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'survey.user_input',
            'view_mode': 'list,form',
            'domain': [
                ('survey_id.is_sustainability', '=', True),
                ('company_id', '=', self.id),
                ('test_entry', '=', False),
            ],
            'context': {'create': False},
        }
    
    @api.depends('name')
    def _compute_sustain_evaluation_count(self):
        for company in self:
            company.sustain_evaluation_count = self.env['survey.user_input'].search_count([
                ('survey_id.is_sustainability', '=', True),
                ('company_id', '=', company.id),
                ('test_entry', '=', False),
            ])
    
    @api.depends('name')
    def _compute_sustain_certification(self):
        """Computa el sello Sostenibilidad más reciente válido de la empresa"""
        for company in self:
            last_cert = self.env['survey.user_input'].search([
                ('company_id', '=', company.id),
                ('survey_id.is_sustainability', '=', True),
                ('state', '=', 'done'),
                ('test_entry', '=', False),
                ('certification_level', '!=', 'none'),
            ], order='create_date desc', limit=1)
            
            if last_cert and last_cert.expiry_date and last_cert.expiry_date >= fields.Date.today():
                company.sustain_certification_level = last_cert.certification_level
                company.sustain_certification_date = fields.Date.from_string(last_cert.create_date)
                company.sustain_expiry_date = last_cert.expiry_date
            else:
                company.sustain_certification_level = 'none'
                company.sustain_certification_date = False
                company.sustain_expiry_date = False
    
    @api.depends('name')
    def _compute_sustain_cert_details(self):
        """Computa puntuación del último examen Sostenibilidad"""
        for company in self:
            last_cert = self.env['survey.user_input'].search([
                ('company_id', '=', company.id),
                ('survey_id.is_sustainability', '=', True),
                ('state', '=', 'done'),
                ('test_entry', '=', False),
                ('certification_level', '!=', 'none'),
            ], order='create_date desc', limit=1)
            
            if last_cert and last_cert.expiry_date and last_cert.expiry_date >= fields.Date.today():
                company.sustain_cert_score = last_cert.scoring_percentage
            else:
                company.sustain_cert_score = 0.0

    def _get_sustainability_positive_items(self):
        """Devuelve lista de dicts con los 3 items positivos hardcodeados de Sostenibilidad.
        
        Los items se muestran si la empresa tiene certificación válida y la
        respuesta correspondiente en el cuestionario alcanza la puntuación mínima.
        Se usa en el template QWeb del microsite. Usa sudo() para contexto público.
        """
        self.ensure_one()
        last_cert = self.env['survey.user_input'].sudo().search([
            ('company_id', '=', self.id),
            ('survey_id.is_sustainability', '=', True),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
            ('certification_level', '!=', 'none'),
        ], order='create_date desc', limit=1)
        
        if not last_cert or not last_cert.expiry_date or last_cert.expiry_date < fields.Date.today():
            return []
        
        lines = last_cert.user_input_line_ids
        questions = last_cert.survey_id.question_ids
        items = []
        
        # Item 1: Ahorro energético (busca pregunta con "energ" en el título)
        q_energy = questions.filtered(lambda q: 'energ' in (q.title or '').lower())
        if q_energy:
            line = lines.filtered(lambda l: l.question_id == q_energy[0])
            if line and line.answer_score >= 1:
                items.append({'label': 'Aplicamos prácticas de ahorro energético', 'icon': 'fa-bolt'})
        
        # Item 2: Gestión de residuos (busca pregunta con "residuo" en el título)
        q_waste = questions.filtered(lambda q: 'residuo' in (q.title or '').lower())
        if q_waste:
            line = lines.filtered(lambda l: l.question_id == q_waste[0])
            if line and line.answer_score >= 1:
                items.append({'label': 'Realizamos una gestión responsable de residuos', 'icon': 'fa-recycle'})
        
        # Item 3: Productos ecológicos/locales (busca pregunta con "ecológ" o "local" o "comunidad")
        q_eco = questions.filtered(lambda q: 'ecológ' in (q.title or '').lower() or 'local' in (q.title or '').lower() or 'comunidad' in (q.title or '').lower())
        if q_eco:
            line = lines.filtered(lambda l: l.question_id == q_eco[0])
            if line and line.answer_score >= 1:
                items.append({'label': 'Ofrecemos productos ecológicos y/o locales', 'icon': 'fa-leaf'})
        
        return items
