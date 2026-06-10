# -*- coding: utf-8 -*-
from odoo import models, fields, api


class MemoriaVivaSettings(models.Model):
    _name = 'memoria.viva.settings'
    _description = 'Configuración de Memoria Viva'
    
    # Singleton pattern
    @api.model
    def get_settings(self):
        settings = self.search([], limit=1)
        if not settings:
            settings = self.create({})
        return settings
    
    # Campos de visibilidad del formulario web
    show_tipo = fields.Boolean(string='Mostrar Tipo', default=False)
    show_categoria = fields.Boolean(string='Mostrar Categoría', default=False)
    show_subcategoria = fields.Boolean(string='Mostrar Subcategoría', default=False)
    show_descripcion_larga = fields.Boolean(string='Mostrar Historia completa', default=False)
    show_coordenadas = fields.Boolean(string='Mostrar Coordenadas', default=False)
    show_mapa = fields.Boolean(string='Mostrar Mapa en listado', default=False)
    show_nombre_publicador = fields.Boolean(string='Mostrar nombre del publicador', default=True)
    show_only_firstname = fields.Boolean(string='Mostrar solo primer nombre', default=True)
    
    # Configuración de likes
    likes_cookie_days = fields.Integer(string='Días de cookie para likes', default=365)
    
    # Configuración de filtros en sidebar
    show_reset_filters = fields.Boolean(
        string='Mostrar botón "Quitar filtros"',
        default=True,
        help='Muestra u oculta el botón de papelera para quitar todos los filtros en el sidebar'
    )
    
    # Anuncio promocional
    anuncio_activo = fields.Boolean(string='Mostrar anuncio', default=True)
    anuncio_titulo = fields.Char(string='Título anuncio', default='📸 ¡Participa en nuestro sorteo!')
    anuncio_texto = fields.Text(string='Texto anuncio', 
        default='Sube tu foto histórica antes del 10 de mayo y participa en el sorteo de entradas para el fútbol, baloncesto y voleibol.')
    anuncio_color = fields.Selection([
        ('primary', 'Azul'),
        ('success', 'Verde'),
        ('warning', 'Amarillo'),
        ('danger', 'Rojo'),
        ('info', 'Cyan'),
        ('dark', 'Oscuro')
    ], string='Color del anuncio', default='warning')
    
    # Configuración de comentarios
    permitir_comentarios = fields.Boolean(string='Permitir comentarios', default=True)
    comentarios_por_pagina = fields.Integer(string='Comentarios por página', default=10)
    comentarios_publicos = fields.Boolean(
        string='Comentarios visibles públicamente',
        default=False,
        help='Si está activado, los visitantes pueden ver comentarios sin iniciar sesión. Solo usuarios registrados pueden comentar.'
    )
    palabra_prohibida_ids = fields.One2many(
        'memoria.viva.palabra.prohibida',
        'settings_id',
        string='Palabras prohibidas'
    )
