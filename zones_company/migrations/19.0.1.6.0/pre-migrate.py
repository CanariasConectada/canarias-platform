"""
Migration script to:
1. Fix zone_id foreign key constraint (ON DELETE SET NULL)
2. Clean up ALL orphan ir.model.data references for zones
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    
    _logger.info("=== Migration 19.0.1.6.0: Starting ===")
    
    # 1. Update FK constraint
    _logger.info("Updating zone_id FK constraint...")
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
    _logger.info("FK constraint updated to ON DELETE SET NULL")
    
    # 2. Clean up ALL orphan ir.model.data references (zones that were deleted)
    _logger.info("Cleaning orphan zone data references...")
    cr.execute("""
        DELETE FROM ir_model_data imd
        WHERE imd.model = 'zone'
        AND imd.module = 'zones_company'
        AND NOT EXISTS (
            SELECT 1 FROM zone z WHERE z.id = imd.res_id
        )
    """)
    _logger.info(f"Deleted {cr.rowcount} orphan zone references")
    
    _logger.info("=== Migration 19.0.1.6.0: Complete ===")
