# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    # Campo para identificar usuarios de Lugares de Interés
    is_lugares_interes_user = fields.Boolean(
        string='Usuario Lugares de Interés',
        default=False,
        help='Indica si este contacto es un usuario público de Lugares de Interés'
    )
    
    # DNI/NIE del usuario - obligatorio para Lugares de Interés
    dni = fields.Char(
        string='DNI/NIE',
        size=20,
        help='Documento de identidad del usuario'
    )
