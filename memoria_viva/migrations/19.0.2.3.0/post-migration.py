# -*- coding: utf-8 -*-
"""Migra la configuración del antiguo modelo singleton memoria.viva.settings
a campos website-specific en res.website.

El modelo memoria.viva.settings se elimina en esta versión (su acción abría el
formulario en modo creación y nunca guardaba). Aquí copiamos el registro más
antiguo (el que leía el frontend vía get_settings → search([], limit=1)) a TODOS
los websites para no perder la configuración existente.
"""
import logging

_logger = logging.getLogger(__name__)

# (columna_antigua, campo_nuevo_en_website)
FIELD_MAP = [
    ('show_tipo', 'memoria_viva_show_tipo'),
    ('show_categoria', 'memoria_viva_show_categoria'),
    ('show_subcategoria', 'memoria_viva_show_subcategoria'),
    ('show_descripcion_larga', 'memoria_viva_show_descripcion_larga'),
    ('show_coordenadas', 'memoria_viva_show_coordenadas'),
    ('show_mapa', 'memoria_viva_show_mapa'),
    ('show_nombre_publicador', 'memoria_viva_show_nombre_publicador'),
    ('show_only_firstname', 'memoria_viva_show_only_firstname'),
    ('likes_cookie_days', 'memoria_viva_likes_cookie_days'),
    ('show_reset_filters', 'memoria_viva_show_reset_filters'),
    ('anuncio_activo', 'memoria_viva_anuncio_activo'),
    ('anuncio_titulo', 'memoria_viva_anuncio_titulo'),
    ('anuncio_texto', 'memoria_viva_anuncio_texto'),
    ('anuncio_color', 'memoria_viva_anuncio_color'),
    ('permitir_comentarios', 'memoria_viva_permitir_comentarios'),
    ('comentarios_por_pagina', 'memoria_viva_comentarios_por_pagina'),
    ('comentarios_publicos', 'memoria_viva_comentarios_publicos'),
]


def migrate(cr, version):
    if not version:
        return

    # La tabla puede no existir si el módulo se instaló ya sin el modelo.
    cr.execute(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = 'memoria_viva_settings'"
    )
    if not cr.fetchone():
        _logger.info("memoria_viva: no existe tabla antigua, nada que migrar.")
        return

    old_cols = [old for old, _new in FIELD_MAP]
    cr.execute(
        "SELECT %s FROM memoria_viva_settings ORDER BY id LIMIT 1"
        % ", ".join(old_cols)
    )
    row = cr.fetchone()
    if not row:
        _logger.info("memoria_viva: tabla antigua vacía, nada que migrar.")
        return

    values = {new: row[i] for i, (_old, new) in enumerate(FIELD_MAP)
              if row[i] is not None}
    if not values:
        return

    # Aplicar a todos los websites vía ORM (respeta tipos/relaciones).
    from odoo import api, SUPERUSER_ID
    env = api.Environment(cr, SUPERUSER_ID, {})
    websites = env['website'].search([])
    if websites:
        websites.write(values)
        _logger.info(
            "memoria_viva: configuración migrada a %s website(s): %s",
            len(websites), list(values.keys()),
        )
