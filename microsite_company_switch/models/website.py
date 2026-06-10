from odoo import models, fields, api

class Website(models.Model):
    _inherit = 'website'
    
    @api.model
    def get_website_for_company(self, company_id):
        """Obtiene el website principal para una compañía específica"""
        # Primero buscar si la compañía tiene un main_website_id
        company = self.env['res.company'].browse(company_id)
        if company.exists() and company.main_website_id:
            return company.main_website_id.id
        
        # Buscar cualquier website de esta compañía
        website = self.search([('company_id', '=', company_id)], limit=1)
        return website.id if website else False
