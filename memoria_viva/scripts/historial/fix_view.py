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
        arch = arch.get("en_US", "")
    # Eliminar la condicion t-if para debug
    arch = arch.replace('t-if="config and config.permitir_comentarios"', 't-if="1"')
    view.write({'arch_db': arch})
    env.cr.commit()
    print("Condition removed - comments should show now")
else:
    print("View not found")

cr.close()
