# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MemoriaVivaEvento(models.Model):
    _name = 'memoria.viva.evento'
    _description = 'Evento del lugar'
    _order = 'mes_numero, name'
    
    # ========================================
    # CAMPOS PRINCIPALES
    # ========================================
    name = fields.Char(string='Nombre del evento', required=True)
    mes = fields.Selection([
        ('1', 'Enero'),
        ('2', 'Febrero'),
        ('3', 'Marzo'),
        ('4', 'Abril'),
        ('5', 'Mayo'),
        ('6', 'Junio'),
        ('7', 'Julio'),
        ('8', 'Agosto'),
        ('9', 'Septiembre'),
        ('10', 'Octubre'),
        ('11', 'Noviembre'),
        ('12', 'Diciembre'),
    ], string='Mes', required=True)
    mes_numero = fields.Integer(string='Número mes', compute='_compute_mes_numero', store=True)
    descripcion = fields.Text(string='Descripción del evento')
    fecha_especifica = fields.Date(string='Fecha específica (opcional)')
    
    # Relación con el lugar
    historia_id = fields.Many2one(
        'memoria.viva.historia', 
        string='Lugar', 
        required=True, 
        ondelete='cascade'
    )
    
    # Campos relacionados del lugar (para mostrar en vistas)
    lugar_name = fields.Char(related='historia_id.name', string='Lugar', store=True)
    website_primario_id = fields.Many2one(related='historia_id.website_primario_id', string='Microsite', store=True)
    
    # Estado del evento
    state = fields.Selection([
        ('activo', 'Activo'),
        ('finalizado', 'Finalizado'),
        ('cancelado', 'Cancelado'),
    ], string='Estado', default='activo', required=True)
    
    active = fields.Boolean(string='Activo', default=True)

    # ========================================
    # COMPUTE METHODS
    # ========================================
    @api.depends('mes')
    def _compute_mes_numero(self):
        for record in self:
            record.mes_numero = int(record.mes) if record.mes else 0

    # ========================================
    # MÉTODOS OVERRIDE
    # ========================================
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Si viene fecha específica, podemos inferir el mes
            if vals.get('fecha_especifica') and not vals.get('mes'):
                from datetime import datetime
                fecha = fields.Date.from_string(vals['fecha_especifica'])
                vals['mes'] = str(fecha.month)
        return super(MemoriaVivaEvento, self).create(vals_list)

    def name_get(self):
        """Mostrar nombre del evento con mes"""
        result = []
        for record in self:
            mes_nombre = dict(self._fields['mes'].selection).get(record.mes, '')
            name = f"{record.name} ({mes_nombre})"
            result.append((record.id, name))
        return result
