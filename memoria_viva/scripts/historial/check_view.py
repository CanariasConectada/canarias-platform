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
    print(f"View name: {view.name}")
    print(f"View key: {view.key}")
    # Check arch_db
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get("en_US", "")
    if arch:
        print(f"Arch length: {len(arch)}")
        if "comentarioForm" in str(arch):
            print("comentarioForm found in arch")
        else:
            print("comentarioForm NOT found in arch")
            # Mostrar las últimas líneas del arch
            print("Last 500 chars of arch:")
            print(str(arch)[-500:])
    else:
        print("Arch is empty")
else:
    print("View not found")

cr.close()
