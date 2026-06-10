# -*- coding: utf-8 -*-
from odoo import models, api
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    def _get_microsite_url(self):
        """Obtiene la URL del microsite de la compañía del producto."""
        self.ensure_one()
        
        if not self.company_id:
            return None
        
        # Buscar el website (microsite) de esta compañía
        website = self.env['website'].sudo().search([
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if website and website.domain:
            return website.domain.rstrip('/')
        
        return None
    
    def get_product_microsite_url(self):
        """Genera la URL completa del producto en su microsite."""
        self.ensure_one()
        
        microsite_base = self._get_microsite_url()
        if not microsite_base:
            return None
        
        # Generar la URL del producto
        slug = self.env['ir.http']._slug(self)
        return f"{microsite_base}/shop/{slug}"


class ProductProduct(models.Model):
    _inherit = 'product.product'
    
    def get_product_microsite_url(self):
        """Genera la URL completa del producto en su microsite."""
        self.ensure_one()
        return self.product_tmpl_id.get_product_microsite_url()
