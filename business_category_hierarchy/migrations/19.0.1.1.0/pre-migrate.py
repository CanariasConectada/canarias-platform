"""
Migration to clean up orphan ir.model.data references for business.category.
This prevents deleted categories from being recreated on module update.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    
    _logger.info("=== Migration: Cleaning orphan business.category references ===")
    
    # Find and delete ir.model.data records that reference non-existent business.category records
    cr.execute("""
        DELETE FROM ir_model_data imd
        WHERE imd.model = 'business.category'
        AND imd.module = 'business_category_hierarchy'
        AND NOT EXISTS (
            SELECT 1 FROM business_category bc WHERE bc.id = imd.res_id
        )
    """)
    
    deleted = cr.rowcount
    _logger.info(f"=== Migration: Deleted {deleted} orphan references ===")
