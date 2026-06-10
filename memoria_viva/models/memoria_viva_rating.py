# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MemoriaVivaRating(models.Model):
    _name = 'memoria.viva.rating'
    _description = 'Valoración de Lugar - Memoria Viva'
    _order = 'create_date desc'
    
    lugar_id = fields.Many2one(
        'memoria.viva.historia', 
        string='Lugar', 
        required=True, 
        ondelete='cascade'
    )
    user_id = fields.Many2one(
        'res.users', 
        string='Usuario', 
        required=True, 
        ondelete='cascade'
    )
    rating = fields.Integer(
        string='Estrellas', 
        required=True,
        help='Valoración de 1 a 5 estrellas'
    )
    
    _sql_constraints = [
        ('unique_user_lugar_rating', 
         'unique(lugar_id, user_id)', 
         'Ya has valorado este lugar. Solo puedes valorar una vez.')
    ]
    
    @api.constrains('rating')
    def _check_rating_range(self):
        for record in self:
            if record.rating < 1 or record.rating > 5:
                raise models.ValidationError(
                    'La valoración debe estar entre 1 y 5 estrellas.'
                )


class MemoriaVivaHistoria(models.Model):
    _inherit = 'memoria.viva.historia'
    
    rating_ids = fields.One2many(
        'memoria.viva.rating', 
        'lugar_id', 
        string='Valoraciones'
    )
    rating_avg = fields.Float(
        string='Valoración Promedio',
        compute='_compute_rating_stats',
        store=True,
        digits=(2, 1)
    )
    rating_count = fields.Integer(
        string='Total Valoraciones',
        compute='_compute_rating_stats',
        store=True
    )
    user_rating = fields.Integer(
        string='Tu Valoración',
        compute='_compute_user_rating'
    )
    
    @api.depends('rating_ids', 'rating_ids.rating')
    def _compute_rating_stats(self):
        for lugar in self:
            ratings = lugar.rating_ids.mapped('rating')
            if ratings:
                lugar.rating_avg = sum(ratings) / len(ratings)
                lugar.rating_count = len(ratings)
            else:
                lugar.rating_avg = 0
                lugar.rating_count = 0
    
    def _compute_user_rating(self):
        for lugar in self:
            # Este campo se computa en el contexto del usuario actual
            # Se usa en el controlador web, no en backend directamente
            lugar.user_rating = 0
