# -*- coding: utf-8 -*-
"""Pre-migration 19.0.1.2.0

Elimina TODAS las ir.rule de zca_platform de la BD antes de que Odoo
recargue el ir_rule.xml. Necesario porque:
- noupdate="0" actualiza registros existentes pero NO borra los que
  desaparecen del XML. Sin este paso quedarían reglas huérfanas activas.
- La versión anterior tenía 25 reglas (incluyendo reglas admin muertas
  y dominios con llamadas ORM). La nueva tiene 13 reglas limpias.
"""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    _logger.info("ZCA pre-migration %s: eliminando ir.rule antiguas", version)

    # Borrar primero los registros de ir.rule referenciados
    cr.execute("""
        DELETE FROM ir_rule
         WHERE id IN (
             SELECT res_id FROM ir_model_data
              WHERE module = 'zca_platform' AND model = 'ir.rule'
         )
    """)

    # Limpiar ir_model_data para que Odoo los recree frescos desde el XML
    cr.execute("""
        DELETE FROM ir_model_data
         WHERE module = 'zca_platform' AND model = 'ir.rule'
    """)

    _logger.info("ZCA pre-migration %s: ir.rule eliminadas", version)
