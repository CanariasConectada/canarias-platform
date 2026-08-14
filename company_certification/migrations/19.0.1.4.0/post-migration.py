# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Traduce los menús generados a todos los idiomas instalados.

Los dos menús hijos de cada vertical ("Mis evaluaciones" y "Nueva
evaluación") los crea ``_ensure_menu`` llamando a ``_()``, que resuelve en
el idioma en que corriera la instalación y guarda el resultado sólo bajo esa
clave del campo traducible. En esta base de datos quedaron con ``en_US``
únicamente, así que un backend en español mostraba "My Evaluations" con la
traducción correcta sin usar en ``i18n/es.po``.

Desde 19.0.1.4.0 ``_sync_menu()`` escribe una etiqueta por idioma instalado.
Aquí se ejecuta una vez sobre lo que ya existe.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    types = (
        env["certification.type"]
        .with_context(active_test=False)
        .search([("menu_id", "!=", False)])
    )
    if not types:
        return

    types._sync_menu_child_names()
    _logger.info(
        "company_certification: menús traducidos para %s verticales en %s idiomas.",
        len(types),
        len(env["res.lang"].get_installed()),
    )
