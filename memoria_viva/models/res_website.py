# -*- coding: utf-8 -*-
"""Configuración de Memoria Viva almacenada de forma website-specific.

Patrón OCA/Odoo: en lugar de un modelo singleton propio (frágil y propenso a
duplicados), la configuración vive como campos en el modelo ``website`` y se
edita desde Ajustes mediante ``res.config.settings`` (ver res_config_settings.py).
El frontend lee estos valores con ``request.website`` (acceso por atributo).
"""
from odoo import fields, models


class Website(models.Model):
    _inherit = 'website'

    # --- Disponibilidad de la página pública ---
    memoria_viva_enabled = fields.Boolean(
        string='Memoria Viva habilitada', default=False,
        help='Activa la página /memoria-viva en este sitio web/microsite')

    # --- Visibilidad del formulario web ---
    memoria_viva_show_tipo = fields.Boolean(
        string='Mostrar Tipo', default=False)
    memoria_viva_show_categoria = fields.Boolean(
        string='Mostrar Categoría', default=False)
    memoria_viva_show_subcategoria = fields.Boolean(
        string='Mostrar Subcategoría', default=False)
    memoria_viva_show_descripcion_larga = fields.Boolean(
        string='Mostrar Historia completa', default=False)
    memoria_viva_show_coordenadas = fields.Boolean(
        string='Mostrar Coordenadas', default=False)
    memoria_viva_show_mapa = fields.Boolean(
        string='Mostrar Mapa en listado', default=False)
    memoria_viva_show_nombre_publicador = fields.Boolean(
        string='Mostrar nombre del publicador', default=True)
    memoria_viva_show_only_firstname = fields.Boolean(
        string='Mostrar solo primer nombre', default=True)

    # --- Sistema de likes ---
    memoria_viva_likes_cookie_days = fields.Integer(
        string='Días de cookie para likes', default=365)

    # --- Filtros del sidebar ---
    memoria_viva_show_reset_filters = fields.Boolean(
        string='Mostrar botón "Quitar filtros"', default=True,
        help='Muestra u oculta el botón de papelera para quitar todos los '
             'filtros en el sidebar')

    # --- Anuncio promocional ---
    memoria_viva_anuncio_activo = fields.Boolean(
        string='Mostrar anuncio', default=True)
    memoria_viva_anuncio_titulo = fields.Char(
        string='Título anuncio', default='📸 ¡Participa en nuestro sorteo!')
    memoria_viva_anuncio_texto = fields.Text(
        string='Texto anuncio',
        default='Sube tu foto histórica antes del 10 de mayo y participa en el '
                'sorteo de entradas para el fútbol, baloncesto y voleibol.')
    memoria_viva_anuncio_color = fields.Selection([
        ('primary', 'Azul'),
        ('success', 'Verde'),
        ('warning', 'Amarillo'),
        ('danger', 'Rojo'),
        ('info', 'Cyan'),
        ('dark', 'Oscuro'),
    ], string='Color del anuncio', default='warning')

    # --- Comentarios ---
    memoria_viva_permitir_comentarios = fields.Boolean(
        string='Permitir comentarios', default=True)
    memoria_viva_comentarios_por_pagina = fields.Integer(
        string='Comentarios por página', default=10)
    memoria_viva_comentarios_publicos = fields.Boolean(
        string='Comentarios visibles públicamente', default=False,
        help='Si está activado, los visitantes pueden ver comentarios sin '
             'iniciar sesión. Solo usuarios registrados pueden comentar.')
