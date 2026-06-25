# -*- coding: utf-8 -*-
"""Capa res.config.settings para editar la configuración de Memoria Viva.

Los campos son ``related`` a ``website_id`` (website-specific), por lo que el
selector de website de la página de Ajustes de Website determina sobre qué
website se guardan los valores. Sustituye al antiguo modelo singleton
``memoria.viva.settings`` (que provocaba duplicados y no guardaba).
"""
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # --- Disponibilidad de la página pública ---
    memoria_viva_enabled = fields.Boolean(
        related='website_id.memoria_viva_enabled', readonly=False)

    # --- Visibilidad del formulario web ---
    memoria_viva_show_tipo = fields.Boolean(
        related='website_id.memoria_viva_show_tipo', readonly=False)
    memoria_viva_show_categoria = fields.Boolean(
        related='website_id.memoria_viva_show_categoria', readonly=False)
    memoria_viva_show_subcategoria = fields.Boolean(
        related='website_id.memoria_viva_show_subcategoria', readonly=False)
    memoria_viva_show_descripcion_larga = fields.Boolean(
        related='website_id.memoria_viva_show_descripcion_larga', readonly=False)
    memoria_viva_show_coordenadas = fields.Boolean(
        related='website_id.memoria_viva_show_coordenadas', readonly=False)
    memoria_viva_show_mapa = fields.Boolean(
        related='website_id.memoria_viva_show_mapa', readonly=False)
    memoria_viva_show_nombre_publicador = fields.Boolean(
        related='website_id.memoria_viva_show_nombre_publicador', readonly=False)
    memoria_viva_show_only_firstname = fields.Boolean(
        related='website_id.memoria_viva_show_only_firstname', readonly=False)

    # --- Sistema de likes ---
    memoria_viva_likes_cookie_days = fields.Integer(
        related='website_id.memoria_viva_likes_cookie_days', readonly=False)

    # --- Filtros del sidebar ---
    memoria_viva_show_reset_filters = fields.Boolean(
        related='website_id.memoria_viva_show_reset_filters', readonly=False)

    # --- Anuncio promocional ---
    memoria_viva_anuncio_activo = fields.Boolean(
        related='website_id.memoria_viva_anuncio_activo', readonly=False)
    memoria_viva_anuncio_titulo = fields.Char(
        related='website_id.memoria_viva_anuncio_titulo', readonly=False)
    memoria_viva_anuncio_texto = fields.Text(
        related='website_id.memoria_viva_anuncio_texto', readonly=False)
    memoria_viva_anuncio_color = fields.Selection(
        related='website_id.memoria_viva_anuncio_color', readonly=False)

    # --- Comentarios ---
    memoria_viva_permitir_comentarios = fields.Boolean(
        related='website_id.memoria_viva_permitir_comentarios', readonly=False)
    memoria_viva_comentarios_por_pagina = fields.Integer(
        related='website_id.memoria_viva_comentarios_por_pagina', readonly=False)
    memoria_viva_comentarios_publicos = fields.Boolean(
        related='website_id.memoria_viva_comentarios_publicos', readonly=False)
