# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import datetime


class MemoriaVivaLike(models.Model):
    _name = 'memoria.viva.like'
    _description = 'Like de Memoria Viva'
    _order = 'create_date desc'
    
    lugar_id = fields.Many2one('memoria.viva.historia', string='Lugar', required=True, ondelete='cascade')
    session_id = fields.Char(string='ID de Sesión', required=True, index=True)
    ip_address = fields.Char(string='Dirección IP')
    liked_at = fields.Datetime(string='Fecha del like', default=lambda self: fields.Datetime.now())
    
    _sql_constraints = [
        ('unique_session_lugar', 'unique(lugar_id, session_id)', 'Ya has dado like a este lugar')
    ]


class MemoriaVivaHistoria(models.Model):
    _inherit = 'memoria.viva.historia'
    
    like_count = fields.Integer(string='Likes', compute='_compute_like_count', store=True)
    like_ids = fields.One2many('memoria.viva.like', 'lugar_id', string='Likes')
    
    @api.depends('like_ids')
    def _compute_like_count(self):
        for lugar in self:
            lugar.like_count = len(lugar.like_ids)
    
    def has_user_liked(self, session_id):
        self.ensure_one()
        return self.like_ids.filtered(lambda l: l.session_id == session_id)
