#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

# Get the website view (ID 11527)
view = env["ir.ui.view"].browse(11527)
if view.exists():
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Remove debug text
    arch = arch.replace('<h2 style="color:red; font-size:30px;">COMENTARIOS SECTION VISIBLE</h2>', '')
    arch = arch.replace('<!-- Sección de Comentarios -->', '')
    arch = arch.replace('<!-- DEBUG: config=<t t-esc="config"/>, permitir=<t t-esc="config.permitir_comentarios if config else \'NO CONFIG\'"/> -->', '')
    
    # Restore original condition
    arch = arch.replace('t-if="True"', 't-if="config.permitir_comentarios"')
    arch = arch.replace('t-if="1"', 't-if="config.permitir_comentarios"')
    
    view.write({'arch_db': arch})
    env.cr.commit()
    print("View cleaned up successfully")
else:
    print("View not found")

cr.close()
