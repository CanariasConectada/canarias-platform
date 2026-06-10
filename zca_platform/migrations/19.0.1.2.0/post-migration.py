# -*- coding: utf-8 -*-
"""Post-migration 19.0.1.2.0

Aplica fixes de BD tras cargar el nuevo ir_rule.xml:
- OdooBot sin empresa.
- Partners de usuarios anclados a su empresa.
- Partners de empresas con company_id correcto.
- Parámetros de sistema (catálogo no compartido).
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
