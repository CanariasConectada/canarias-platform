# Copyright 2026 Tu Empresa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migrar business_category_id (Many2one) a business_category_ids (Many2many).

    Crea la tabla de relación y migra los datos existentes sin pérdida.
    """
    _logger.info("[MIGRATE] Iniciando migración de business_category_id a Many2many")

    # Crear tabla de relación si no existe
    cr.execute("""
        CREATE TABLE IF NOT EXISTS res_company_business_category_rel (
            res_company_id INTEGER NOT NULL REFERENCES res_company(id) ON DELETE CASCADE,
            business_category_id INTEGER NOT NULL REFERENCES business_category(id) ON DELETE CASCADE,
            PRIMARY KEY (res_company_id, business_category_id)
        )
    """)

    # Migrar datos existentes del campo Many2one
    cr.execute("""
        INSERT INTO res_company_business_category_rel (res_company_id, business_category_id)
        SELECT id, business_category_id
        FROM res_company
        WHERE business_category_id IS NOT NULL
        ON CONFLICT (res_company_id, business_category_id) DO NOTHING
    """)

    migrated = cr.rowcount
    _logger.info("[MIGRATE] %s empresas migradas a Many2many", migrated)
