# -*- coding: utf-8 -*-
from odoo import models, fields


class LugaresInteresTipo(models.Model):
    _name = 'lugares.interes.tipo'
    _description = 'Tipo de Lugar - Nivel 1'
    _order = 'sequence, name'

    name = fields.Char(string='Tipo', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    
    categoria_ids = fields.One2many(
        'lugares.interes.categoria', 
        'tipo_id', 
        string='Categorías'
    )
    
    categoria_count = fields.Integer(
        string='Nº Categorías',
        compute='_compute_categoria_count'
    )

    def _compute_categoria_count(self):
        for tipo in self:
            tipo.categoria_count = len(tipo.categoria_ids)
