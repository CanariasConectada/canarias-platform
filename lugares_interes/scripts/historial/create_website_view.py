#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

# Get the base view
base_view = env["ir.ui.view"].search([("key", "=", "lugares_interes.lugares_interes_detail"), ("website_id", "=", False)])
if base_view:
    # Create website-specific view
    website_id = 229  # Guanarteme
    arch = base_view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    website_view_vals = {
        'name': base_view.name,
        'key': base_view.key,
        'type': 'qweb',
        'arch_db': arch,
        'website_id': website_id,
        'mode': 'primary',
    }
    
    # Check if it already exists
    existing = env["ir.ui.view"].search([("key", "=", base_view.key), ("website_id", "=", website_id)])
    if existing:
        print(f"Website view already exists: ID {existing.id}")
    else:
        new_view = env["ir.ui.view"].create(website_view_vals)
        env.cr.commit()
        print(f"Website view created: ID {new_view.id}")
else:
    print("Base view not found")

cr.close()
