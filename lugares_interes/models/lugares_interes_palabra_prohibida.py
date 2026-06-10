# -*- coding: utf-8 -*-
from odoo import models, fields


class LugaresInteresPalabraProhibida(models.Model):
    _name = 'lugares.interes.palabra.prohibida'
    _description = 'Palabra Prohibida - Lugares de Interés'
    _order = 'name'

    name = fields.Char(string='Palabra', required=True, translate=False)
    active = fields.Boolean(string='Activa', default=True)
    settings_id = fields.Many2one('lugares.interes.settings', string='Configuración')
    
    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Esta palabra ya está en la lista.')
    ]
