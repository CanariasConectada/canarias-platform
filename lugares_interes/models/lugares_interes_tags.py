# -*- coding: utf-8 -*-
from odoo import models, fields


class LugaresInteresPublicoObjetivo(models.Model):
    _name = 'lugares.interes.publico.objetivo'
    _description = 'Público Objetivo (Tag)'
    _order = 'sequence, name'

    name = fields.Char(string='Público', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    color = fields.Integer(string='Color', default=0)


class LugaresInteresMomentoDia(models.Model):
    _name = 'lugares.interes.momento.dia'
    _description = 'Momento del Día (Tag)'
    _order = 'sequence, name'

    name = fields.Char(string='Momento', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    color = fields.Integer(string='Color', default=0)


class LugaresInteresAmbiente(models.Model):
    _name = 'lugares.interes.ambiente'
    _description = 'Ambiente (Tag)'
    _order = 'sequence, name'

    name = fields.Char(string='Ambiente', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    color = fields.Integer(string='Color', default=0)


class LugaresInteresExperiencia(models.Model):
    _name = 'lugares.interes.experiencia'
    _description = 'Experiencia (Tag)'
    _order = 'sequence, name'

    name = fields.Char(string='Experiencia', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    color = fields.Integer(string='Color', default=0)


class LugaresInteresFiestaEvento(models.Model):
    _name = 'lugares.interes.fiesta.evento'
    _description = 'Fiesta o Evento (Tag)'
    _order = 'name'

    name = fields.Char(string='Evento/Fiesta', required=True, translate=True)
    frecuencia = fields.Selection([
        ('anual', 'Anual'),
        ('mensual', 'Mensual'),
        ('periodica', 'Periódica'),
        ('unica', 'Única vez'),
    ], string='Frecuencia', default='anual')
    
    mes_inicio = fields.Selection([
        ('1', 'Enero'), ('2', 'Febrero'), ('3', 'Marzo'),
        ('4', 'Abril'), ('5', 'Mayo'), ('6', 'Junio'),
        ('7', 'Julio'), ('8', 'Agosto'), ('9', 'Septiembre'),
        ('10', 'Octubre'), ('11', 'Noviembre'), ('12', 'Diciembre'),
    ], string='Mes de inicio')
    
    descripcion = fields.Text(string='Descripción')
    active = fields.Boolean(string='Activo', default=True)
