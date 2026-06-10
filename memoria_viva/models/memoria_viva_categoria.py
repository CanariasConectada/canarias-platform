# -*- coding: utf-8 -*-
from odoo import models, fields


class MemoriaVivaCategoria(models.Model):
    _name = 'memoria.viva.categoria'
    _description = 'Categoría de Lugar - Nivel 2'
    _order = 'tipo_id, sequence, name'

    name = fields.Char(string='Categoría', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    
    tipo_id = fields.Many2one(
        'memoria.viva.tipo', 
        string='Tipo Padre', 
        required=True,
        ondelete='restrict'
    )
    
    subcategoria_ids = fields.One2many(
        'memoria.viva.subcategoria', 
        'categoria_id', 
        string='Subcategorías'
    )
    
    subcategoria_count = fields.Integer(
        string='Nº Subcategorías',
        compute='_compute_subcategoria_count'
    )

    def _compute_subcategoria_count(self):
        for cat in self:
            cat.subcategoria_count = len(cat.subcategoria_ids)
