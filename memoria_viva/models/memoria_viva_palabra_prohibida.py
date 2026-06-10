# -*- coding: utf-8 -*-
from odoo import models, fields


class MemoriaVivaPalabraProhibida(models.Model):
    _name = 'memoria.viva.palabra.prohibida'
    _description = 'Palabra Prohibida - Memoria Viva'
    _order = 'name'

    name = fields.Char(string='Palabra', required=True, translate=False)
    active = fields.Boolean(string='Activa', default=True)
    settings_id = fields.Many2one('memoria.viva.settings', string='Configuración')
    
    _sql_constraints = [
        ('unique_name', 'unique(name)', 'Esta palabra ya está en la lista.')
    ]
