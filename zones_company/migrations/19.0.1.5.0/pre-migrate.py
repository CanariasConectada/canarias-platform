"""
Migration script to fix zone_id foreign key constraint.
Changes from ON DELETE RESTRICT to ON DELETE SET NULL.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Pre-migration: Update the foreign key constraint on res_company.zone_id
    to use ON DELETE SET NULL instead of ON DELETE RESTRICT.
    """
    if not version:
        return
    
    _logger.info("=== Migration: Updating zone_id FK constraint ===")
    
    # Find existing constraints related to zone_id
    cr.execute("""
        SELECT conname 
        FROM pg_constraint 
        WHERE conrelid = 'res_company'::regclass 
        AND conname LIKE '%zone%'
    """)
    constraints = cr.fetchall()
    
    _logger.info(f"Found constraints: {constraints}")
    
    # Drop all zone-related constraints
    for (constraint_name,) in constraints:
        _logger.info(f"Dropping constraint: {constraint_name}")
        cr.execute(f'ALTER TABLE res_company DROP CONSTRAINT IF EXISTS "{constraint_name}"')
    
    # Also check for the standard naming convention
    cr.execute("""
        ALTER TABLE res_company 
        DROP CONSTRAINT IF EXISTS res_company_zone_id_fkey
    """)
    
    # Recreate with ON DELETE SET NULL
    cr.execute("""
        ALTER TABLE res_company 
        ADD CONSTRAINT res_company_zone_id_fkey 
        FOREIGN KEY (zone_id) REFERENCES zone(id) 
        ON DELETE SET NULL
    """)
    
    _logger.info("=== Migration: FK constraint updated to ON DELETE SET NULL ===")
