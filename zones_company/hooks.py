import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


# Zonas iniciales - se crean solo si no existen, sin ir.model.data
DEFAULT_ZONES = [
    {'name': 'Guanarteme', 'code': 'GUA', 'description': 'Zona de Guanarteme.', 'sequence': 10},
    {'name': 'Tamaraceite', 'code': 'TAM', 'description': 'Zona de Tamaraceite.', 'sequence': 20},
    {'name': 'Lomo los Frailes', 'code': 'LOM', 'description': 'Zona de Lomo los Frailes.', 'sequence': 30},
    {'name': 'Ninguna', 'code': 'NIN', 'description': 'Sin zona asignada.', 'sequence': 999},
]


def post_init_hook(cr, registry):
    """
    Post-init hook para:
    1. Actualizar FK constraint
    2. Crear zonas iniciales (sin ir.model.data)
    3. Configurar reglas de partners
    4. Corregir valores NULL en campos requeridos de res.company
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # ===== 1. Actualizar FK constraint =====
    _logger.info("Actualizando FK constraint de zone_id...")
    cr.execute("""
        SELECT conname FROM pg_constraint 
        WHERE conrelid = 'res_company'::regclass AND conname LIKE '%zone%'
    """)
    for (name,) in cr.fetchall():
        cr.execute(f'ALTER TABLE res_company DROP CONSTRAINT IF EXISTS "{name}"')
    
    cr.execute("ALTER TABLE res_company DROP CONSTRAINT IF EXISTS res_company_zone_id_fkey")
    cr.execute("""
        ALTER TABLE res_company ADD CONSTRAINT res_company_zone_id_fkey 
        FOREIGN KEY (zone_id) REFERENCES zone(id) ON DELETE SET NULL
    """)
    
    # ===== 2. Crear zonas iniciales (solo si no existen) =====
    _logger.info("Verificando zonas iniciales...")
    Zone = env['zone']
    for zone_data in DEFAULT_ZONES:
        existing = Zone.search([('code', '=', zone_data['code'])], limit=1)
        if not existing:
            Zone.create(zone_data)
            _logger.info(f"Zona creada: {zone_data['name']}")
    
    # ===== 3. Configurar reglas de partners =====
    rule = env.ref('base.res_partner_portal_public_rule', raise_if_not_found=False)
    portal_group = env.ref('base.group_portal', raise_if_not_found=False)
    public_group = env.ref('base.group_public', raise_if_not_found=False)
    if rule and portal_group and public_group:
        rule.write({'groups': [(6, 0, [portal_group.id, public_group.id])]})
    
    # ===== 4. Corregir valores NULL en campos requeridos =====
    _logger.info("Corrigiendo valores NULL en campos requeridos de res.company...")
    
    # Valores por defecto según las definiciones de los modelos
    defaults = {
        'fiscalyear_last_day': 31,
        'fiscalyear_last_month': '12',
        'account_price_include': 'tax_excluded',
        'inventory_period': 'manual',
        'cost_method': 'standard',
        'account_peppol_proxy_state': 'not_registered',
        'security_lead': 0.0,
        'horizon_days': 365.0,  # Agregado
    }
    
    updates_made = False
    for field_name, default_value in defaults.items():
        # Verificar si hay registros con NULL
        cr.execute(f"""
            SELECT COUNT(*) FROM res_company WHERE {field_name} IS NULL
        """)
        null_count = cr.fetchone()[0]
        
        if null_count > 0:
            _logger.info(f"Inicializando {field_name} con valor por defecto '{default_value}' para {null_count} registro(s)")
            if isinstance(default_value, str):
                cr.execute(f"""
                    UPDATE res_company 
                    SET {field_name} = %s 
                    WHERE {field_name} IS NULL
                """, (default_value,))
            else:
                cr.execute(f"""
                    UPDATE res_company 
                    SET {field_name} = %s 
                    WHERE {field_name} IS NULL
                """, (default_value,))
            updates_made = True
    
    if updates_made:
        cr.commit()
        _logger.info("Valores NULL corregidos. Odoo debería poder agregar las restricciones NOT NULL automáticamente.")
    else:
        _logger.info("No se encontraron valores NULL que corregir.")
    
    # ===== 5. Agregar restricciones NOT NULL directamente =====
    _logger.info("Agregando restricciones NOT NULL directamente...")
    from odoo.tools import sql
    
    added_count = 0
    for field_name, default_value in defaults.items():
        # Verificar si ya tiene NOT NULL
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
        if result and not result[0]:
            # Verificar que no haya valores NULL
            cr.execute(f"SELECT COUNT(*) FROM res_company WHERE {field_name} IS NULL")
            null_count = cr.fetchone()[0]
            
            if null_count == 0:
                try:
                    sql.set_not_null(cr, 'res_company', field_name)
                    _logger.info(f"  ✓ Restricción NOT NULL agregada a {field_name}")
                    added_count += 1
                except Exception as e:
                    _logger.warning(f"  ⚠ No se pudo agregar NOT NULL a {field_name}: {e}")
    
    if added_count > 0:
        cr.commit()
        _logger.info(f"Se agregaron {added_count} restricción(es) NOT NULL.")
    else:
        _logger.info("Todas las restricciones NOT NULL ya estaban presentes o no se pudieron agregar.")
    
    # ===== 6. Fix: Missing not-null constraint en res.config.settings.default_picking_policy =====
    _logger.info("Corrigiendo constraint NOT NULL en res_config_settings.default_picking_policy...")
    
    # Primero actualizar valores NULL
    cr.execute("""
        UPDATE res_config_settings 
        SET default_picking_policy = 'direct' 
        WHERE default_picking_policy IS NULL
    """)
    if cr.rowcount > 0:
        _logger.info(f"  ✓ {cr.rowcount} registro(s) actualizado(s) con valor por defecto 'direct'")
        cr.commit()
    
    # Verificar si ya tiene NOT NULL
    cr.execute("""
        SELECT a.attnotnull
        FROM pg_attribute a
        JOIN pg_class c ON a.attrelid = c.oid
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'public'
        AND c.relname = 'res_config_settings'
        AND a.attname = 'default_picking_policy'
        AND a.attnum > 0
    """)
    result = cr.fetchone()
    
    if result and not result[0]:
        # No tiene NOT NULL, intentar agregar
        cr.execute("SELECT COUNT(*) FROM res_config_settings WHERE default_picking_policy IS NULL")
        null_count = cr.fetchone()[0]
        
        if null_count == 0:
            try:
                sql.set_not_null(cr, 'res_config_settings', 'default_picking_policy')
                cr.commit()
                _logger.info("  ✓ Restricción NOT NULL agregada a default_picking_policy")
            except Exception as e:
                _logger.warning(f"  ⚠ No se pudo agregar NOT NULL a default_picking_policy: {e}")
        else:
            _logger.warning(f"  ⚠ Aún hay {null_count} valores NULL en default_picking_policy")
    else:
        _logger.info("  ✓ default_picking_policy ya tiene restricción NOT NULL")