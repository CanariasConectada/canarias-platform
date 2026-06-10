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
    
    # Add visible text at the very beginning of the comments section
    arch = arch.replace(
        '<!-- Sección de Comentarios -->',
        '<!-- Sección de Comentarios --><h2 style="color:red; font-size:30px;">COMENTARIOS SECTION VISIBLE</h2>'
    )
    
    view.write({'arch_db': arch})
    env.cr.commit()
    print("Visible text added")
else:
    print("View not found")

cr.close()
