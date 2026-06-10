# -*- coding: utf-8 -*-
from odoo import models, fields


class ResPartner(models.Model):
    _inherit = 'res.partner'
    
    # Campo para identificar usuarios de Memoria Viva
    is_memoria_viva_user = fields.Boolean(
        string='Usuario Memoria Viva',
        default=False,
        help='Indica si este contacto es un usuario público de Memoria Viva'
    )
    
    # DNI/NIE del usuario - obligatorio para Memoria Viva
    dni = fields.Char(
        string='DNI/NIE',
        size=20,
        help='Documento de identidad del usuario'
    )
