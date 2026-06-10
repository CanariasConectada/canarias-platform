# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PartnerReviewSettings(models.Model):
    _name = 'partner.review.settings'
    _description = 'Configuración de Reseñas'

    permitir_comentarios = fields.Boolean(
        string='Permitir comentarios',
        default=True,
        help='Si está desactivado, nadie podrá enviar comentarios'
    )
    @api.model
    def get_settings(self):
        settings = self.search([], limit=1)
        if not settings:
            settings = self.create({})
        return settings
