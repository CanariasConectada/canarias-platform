#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

view = env["ir.ui.view"].search([("key", "=", "memoria_viva.memoria_viva_detail")])
if view:
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Change condition to True
    arch = arch.replace('t-if="1"', 't-if="True"')
    
    view.write({'arch_db': arch})
    env.cr.commit()
    print("Condition fixed")
else:
    print("View not found")

cr.close()
