# -*- coding: utf-8 -*-
from odoo import models, fields


class PartnerReviewPalabraProhibida(models.Model):
    _name = 'partner.review.palabra.prohibida'
    _description = 'Palabra Prohibida - Reseñas'
    _order = 'name'

    name = fields.Char(string='Palabra', required=True)
    active = fields.Boolean(string='Activa', default=True)

    def action_activar(self):
        self.write({'active': True})

    def action_desactivar(self):
        self.write({'active': False})
