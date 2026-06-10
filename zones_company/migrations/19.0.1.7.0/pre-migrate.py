"""
Migration to remove ALL ir.model.data references for zones.
This is necessary because we're switching from XML data files to Python hooks.
The zones will be created by post_init_hook without ir.model.data entries.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    
    _logger.info("=== Migration 19.0.1.7.0: Removing ALL zone ir.model.data ===")
    
    # 1. Update FK constraint
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
    _logger.info("FK constraint updated")
    
    # 2. Remove ALL ir.model.data entries for zones (this is the key fix)
    cr.execute("""
        DELETE FROM ir_model_data 
        WHERE model = 'zone' 
        AND module = 'zones_company'
    """)
    _logger.info(f"Deleted {cr.rowcount} ir.model.data entries for zones")
    
    _logger.info("=== Migration 19.0.1.7.0: Complete ===")
