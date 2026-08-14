# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _


class ResCompany(models.Model):
    _inherit = 'res.company'

    silver_certification_level = fields.Selection([
        ('none', 'Sin sello'),
        ('bronze', 'Bronce'),
        ('silver', 'Plata'),
        ('gold', 'Oro'),
    ], string='Nivel Silver Economy', compute='_compute_silver_certification', store=True)
    
    silver_certification_date = fields.Date(
        string='Fecha de certificación Silver',
        compute='_compute_silver_certification',
        store=True
    )
    
    silver_expiry_date = fields.Date(
        string='Expiración sello Silver',
        compute='_compute_silver_certification',
        store=True
    )
    
    silver_evaluation_count = fields.Integer(
        string='Evaluaciones Silver',
        compute='_compute_silver_evaluation_count'
    )
    
    silver_cert_score = fields.Float(
        string='Puntuación Silver Economy (%)',
        compute='_compute_silver_cert_details',
        store=True
    )
    
    def action_open_silver_evaluations(self):
        """Abre el listado de evaluaciones Silver Economy de esta empresa"""
        self.ensure_one()
        return {
            'name': _('Evaluaciones Silver Economy - %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'survey.user_input',
            'view_mode': 'list,form',
            'domain': [
                ('survey_id.is_silver_economy', '=', True),
                ('company_id', '=', self.id),
                ('test_entry', '=', False),
            ],
            'context': {'create': False},
        }
    
    @api.depends('name')
    def _compute_silver_evaluation_count(self):
        for company in self:
            company.silver_evaluation_count = self.env['survey.user_input'].search_count([
                ('survey_id.is_silver_economy', '=', True),
                ('company_id', '=', company.id),
                ('test_entry', '=', False),
            ])
    
    @api.depends('name')
    def _compute_silver_certification(self):
        """Computa el sello Silver Economy más reciente válido de la empresa"""
        for company in self:
            last_cert = self.env['survey.user_input'].search([
                ('company_id', '=', company.id),
                ('survey_id.is_silver_economy', '=', True),
                ('state', '=', 'done'),
                ('test_entry', '=', False),
                ('certification_level', '!=', 'none'),
            ], order='create_date desc', limit=1)
            
            if last_cert and last_cert.expiry_date and last_cert.expiry_date >= fields.Date.today():
                company.silver_certification_level = last_cert.certification_level
                company.silver_certification_date = fields.Date.from_string(last_cert.create_date)
                company.silver_expiry_date = last_cert.expiry_date
            else:
                company.silver_certification_level = 'none'
                company.silver_certification_date = False
                company.silver_expiry_date = False
    
    @api.depends('name')
    def _compute_silver_cert_details(self):
        """Computa puntuación del último examen Silver Economy"""
        for company in self:
            last_cert = self.env['survey.user_input'].search([
                ('company_id', '=', company.id),
                ('survey_id.is_silver_economy', '=', True),
                ('state', '=', 'done'),
                ('test_entry', '=', False),
                ('certification_level', '!=', 'none'),
            ], order='create_date desc', limit=1)
            
            if last_cert and last_cert.expiry_date and last_cert.expiry_date >= fields.Date.today():
                company.silver_cert_score = last_cert.scoring_percentage
            else:
                company.silver_cert_score = 0.0

    def _get_silver_positive_items(self):
        """Devuelve lista de dicts con los items positivos activos de la última evaluación.
        
        Cada dict tiene: {'label': str, 'icon': str}
        Se usa en el template QWeb del microsite.
        Usa sudo() porque puede ejecutarse en contexto público (website).
        """
        self.ensure_one()
        last_cert = self.env['survey.user_input'].sudo().search([
            ('company_id', '=', self.id),
            ('survey_id.is_silver_economy', '=', True),
            ('state', '=', 'done'),
            ('test_entry', '=', False),
            ('certification_level', '!=', 'none'),
        ], order='create_date desc', limit=1)
        
        if not last_cert or not last_cert.expiry_date or last_cert.expiry_date < fields.Date.today():
            return []
        
        survey = last_cert.survey_id
        if not survey.silver_positive_item_ids:
            return []
        
        lines = last_cert.user_input_line_ids
        active_items = []
        for item_config in survey.silver_positive_item_ids.sorted('sequence'):
            line = lines.filtered(lambda l: l.question_id == item_config.question_id)
            if line and line.answer_score >= item_config.min_score:
                active_items.append({
                    'label': item_config.label,
                    'icon': item_config.icon or 'fa-check-circle',
                })
        return active_items
