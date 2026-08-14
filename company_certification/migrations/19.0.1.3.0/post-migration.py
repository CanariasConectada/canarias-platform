# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Reactiva el menú de cada vertical activa.

Los menús que genera ``_ensure_menu`` se archivaron a mano mientras los
módulos ``silver_economy`` / ``sustainability`` seguían instalados, porque
cada vertical aparecía dos veces en el backend. Al jubilar esos módulos
desaparece su árbol de menús y, sin este paso, la vertical se quedaría sin
punto de entrada: el tipo sigue activo pero su menú no.

Hasta 19.0.1.3.0 el estado del menú no seguía al del tipo, así que un
``-u`` no lo arreglaba solo. ``_sync_menu()`` es ahora el dueño de esa
correspondencia; aquí sólo se ejecuta una vez sobre lo que ya está en la
base de datos.
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

    types._sync_menu()
    _logger.info(
        "company_certification: sincronizados los menús de %s verticales (%s activas).",
        len(types),
        len(types.filtered("active")),
    )
