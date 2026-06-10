# -*- coding: utf-8 -*-
"""Post-migration 19.0.1.3.0

Nuevos fixes respecto a 1.2.0:
- Regla global ir.rule para res.partner (limita admin a empresa activa).
- Propagación de group_erp_manager a usuarios con group_system creados vía SQL.
- Limpieza de menús con action huérfana (act_window eliminado).
- Reasignación canónica del menú Contacts si quedó sin action.
- Limpieza de action_id huérfano en res_users (evita pantalla en blanco).
"""
import logging
from odoo.addons.zca_platform.hooks import post_migrate

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _logger.info("ZCA post-migration %s: iniciando", version)
    post_migrate(cr)
    _logger.info("ZCA post-migration %s: completada", version)
