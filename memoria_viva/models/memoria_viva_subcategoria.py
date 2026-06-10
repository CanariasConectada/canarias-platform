# -*- coding: utf-8 -*-
from odoo import models, fields


class MemoriaVivaSubcategoria(models.Model):
    _name = 'memoria.viva.subcategoria'
    _description = 'Subcategoría de Lugar - Nivel 3'
    _order = 'categoria_id, sequence, name'

    name = fields.Char(string='Subcategoría', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    
    categoria_id = fields.Many2one(
        'memoria.viva.categoria', 
        string='Categoría Padre', 
        required=True,
        ondelete='restrict'
    )
    
    tipo_id = fields.Many2one(
        'memoria.viva.tipo',
        related='categoria_id.tipo_id',
        store=True,
        string='Tipo'
    )
