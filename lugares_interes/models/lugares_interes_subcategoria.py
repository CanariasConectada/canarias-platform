# -*- coding: utf-8 -*-
from odoo import models, fields


class LugaresInteresSubcategoria(models.Model):
    _name = 'lugares.interes.subcategoria'
    _description = 'Subcategoría de Lugar - Nivel 3'
    _order = 'categoria_id, sequence, name'

    name = fields.Char(string='Subcategoría', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    
    categoria_id = fields.Many2one(
        'lugares.interes.categoria', 
        string='Categoría Padre', 
        required=True,
        ondelete='restrict'
    )
    
    tipo_id = fields.Many2one(
        'lugares.interes.tipo',
        related='categoria_id.tipo_id',
        store=True,
        string='Tipo'
    )
