# -*- coding: utf-8 -*-
from odoo import models, fields, api
from .memoria_viva_historia import _validate_image


class MemoriaVivaHistoriaImage(models.Model):
    _name = 'memoria.viva.historia.image'
    _description = 'Imagen adicional - Memoria Viva'
    _order = 'sequence, id'

    historia_id = fields.Many2one('memoria.viva.historia', string='Historia', required=True, ondelete='cascade')
    image = fields.Image(string='Imagen', required=True, attachment=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    name = fields.Char(string='Nombre descriptivo')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('image'):
                _validate_image(vals['image'], 'Imagen adicional')
        return super(MemoriaVivaHistoriaImage, self).create(vals_list)

    def write(self, vals):
        if vals.get('image'):
            _validate_image(vals['image'], 'Imagen adicional')
        return super(MemoriaVivaHistoriaImage, self).write(vals)
