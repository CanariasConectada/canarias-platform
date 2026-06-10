"""
Migration to remove ALL ir.model.data references for business.category.
This prevents deleted categories from being recreated on module update.
Categories are now created via post_init_hook without ir.model.data entries.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    
    _logger.info("=== Migration 19.0.1.2.0: Removing ALL category ir.model.data ===")
    
    # Remove ALL ir.model.data entries for business.category
    cr.execute("""
        DELETE FROM ir_model_data 
        WHERE model = 'business.category' 
        AND module = 'business_category_hierarchy'
    """)
    
    _logger.info(f"Deleted {cr.rowcount} ir.model.data entries for categories")
    _logger.info("=== Migration 19.0.1.2.0: Complete ===")
