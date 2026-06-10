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
    print(f"View ID: {view.id}")
    print(f"View type: {view.type}")
    print(f"View mode: {view.mode}")
    print(f"View inherit_id: {view.inherit_id}")
    print(f"View model: {view.model}")
    # Check if arch_db is jsonb
    cr.execute("SELECT pg_typeof(arch_db) FROM ir_ui_view WHERE id = %s", (view.id,))
    result = cr.fetchone()
    print(f"arch_db type: {result[0] if result else 'unknown'}")
else:
    print("View not found")

cr.close()
