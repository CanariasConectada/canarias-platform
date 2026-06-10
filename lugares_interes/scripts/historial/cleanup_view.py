#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

view = env["ir.ui.view"].search([("key", "=", "lugares_interes.lugares_interes_detail")])
if view:
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Remove debug message
    arch = arch.replace('<h1>DEBUG: COMMENTS SECTION SHOULD BE HERE</h1>', '')
    
    # Restore original condition (but keep it as "1" for now to ensure it works)
    # arch = arch.replace('t-if="1"', 't-if="config and config.permitir_comentarios"')
    
    view.write({'arch_db': arch})
    env.cr.commit()
    print("View cleaned up")
else:
    print("View not found")

cr.close()
