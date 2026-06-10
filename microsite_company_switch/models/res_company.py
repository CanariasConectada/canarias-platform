from odoo import models, fields, api

class ResCompany(models.Model):
    _inherit = 'res.company'
    
    # Campo para indicar el website principal de la compañía
    main_website_id = fields.Many2one('website', string='Microsite Principal',
                                      help='Website asociado a esta compañía para redirección automática')
    
    @api.model
    def get_company_website_url(self, company_id):
        """Obtiene la URL del website asociado a una compañía"""
        company = self.browse(company_id)
        if company.main_website_id and company.main_website_id.domain:
            return company.main_website_id.domain
        # Buscar cualquier website de esta compañía
        website = self.env['website'].search([('company_id', '=', company_id)], limit=1)
        if website and website.domain:
            return website.domain
        return False
