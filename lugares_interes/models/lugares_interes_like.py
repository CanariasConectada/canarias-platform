# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime


class LugaresInteresLike(models.Model):
    _name = 'lugares.interes.like'
    _description = 'Like de Lugares de Interés'
    _order = 'create_date desc'
    
    lugar_id = fields.Many2one('lugares.interes.historia', string='Lugar', required=True, ondelete='cascade')
    session_id = fields.Char(string='ID de Sesión', required=True, index=True)
    ip_address = fields.Char(string='Dirección IP')
    liked_at = fields.Datetime(string='Fecha del like', default=lambda self: fields.Datetime.now())
    
    _sql_constraints = [
        ('unique_session_lugar', 'unique(lugar_id, session_id)', 'Ya has dado like a este lugar')
    ]


class LugaresInteresHistoria(models.Model):
    _inherit = 'lugares.interes.historia'
    
    like_count = fields.Integer(string='Likes', compute='_compute_like_count', store=True)
    like_ids = fields.One2many('lugares.interes.like', 'lugar_id', string='Likes')
    
    @api.depends('like_ids')
    def _compute_like_count(self):
        for lugar in self:
            lugar.like_count = len(lugar.like_ids)
    
    def has_user_liked(self, session_id):
        self.ensure_one()
        return self.like_ids.filtered(lambda l: l.session_id == session_id)
