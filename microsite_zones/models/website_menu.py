# -*- coding: utf-8 -*-
"""
Extensión del modelo website.menu para agregar soporte multicompany.
"""

from odoo import models, fields


class WebsiteMenu(models.Model):
    _inherit = 'website.menu'
    
    # Campo company_id relacionado al website
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='website_id.company_id',
        store=True,
        readonly=True,
    )
