import logging

from odoo import models, fields, api
from odoo.tools import sql

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = 'res.company'

    zone_id = fields.Many2one(
        'zone',
        string='Zona',
        ondelete='set null',  # Permite eliminar zonas, las empresas quedan sin zona
        index=True
    )

    def init(self):
        """
        Este método se ejecuta después de _auto_init en cada arranque de Odoo.
        Asegura que las restricciones NOT NULL estén presentes en los campos requeridos.
        """
        super().init()
        
        # Campos que deben tener NOT NULL con sus valores por defecto
        required_fields = {
            'fiscalyear_last_day': 31,
            'fiscalyear_last_month': '12',
            'account_price_include': 'tax_excluded',
            'inventory_period': 'manual',
            'cost_method': 'standard',
            'account_peppol_proxy_state': 'not_registered',
            'security_lead': 0.0,
            'horizon_days': 365.0,
        }
        
        cr = self.env.cr
        added_count = 0
        
        for field_name, default_value in required_fields.items():
            # Verificar si la columna existe
            cr.execute("""
                SELECT a.attnotnull
                FROM pg_attribute a
                JOIN pg_class c ON a.attrelid = c.oid
                JOIN pg_namespace n ON c.relnamespace = n.oid
                WHERE n.nspname = 'public'
                AND c.relname = 'res_company'
                AND a.attname = %s
                AND a.attnum > 0
            """, (field_name,))
            
            result = cr.fetchone()
            if not result:
                # Columna no existe, saltar
                continue
            
            has_notnull = result[0]
            
            if not has_notnull:
                # Primero, asegurar que no hay valores NULL
                cr.execute(f"SELECT COUNT(*) FROM res_company WHERE {field_name} IS NULL")
                null_count = cr.fetchone()[0]
                
                if null_count > 0:
                    # Inicializar valores NULL con el default
                    cr.execute(f"""
                        UPDATE res_company 
                        SET {field_name} = %s 
                        WHERE {field_name} IS NULL
                    """, (default_value,))
                    _logger.info(f"zones_company.init: Inicializado {field_name} con '{default_value}' para {null_count} registro(s)")
                
                # Agregar restricción NOT NULL
                try:
                    sql.set_not_null(cr, 'res_company', field_name)
                    _logger.info(f"zones_company.init: Restricción NOT NULL agregada a {field_name}")
                    added_count += 1
                except Exception as e:
                    _logger.warning(f"zones_company.init: No se pudo agregar NOT NULL a {field_name}: {e}")
        
        if added_count > 0:
            _logger.info(f"zones_company.init: Se agregaron {added_count} restricción(es) NOT NULL a res_company")
