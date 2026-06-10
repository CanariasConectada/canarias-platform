#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID
import json

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

# Get raw arch_db from database
cr.execute("SELECT arch_db FROM ir_ui_view WHERE key = 'memoria_viva.memoria_viva_detail'")
result = cr.fetchone()
if result:
    arch_db = result[0]
    print(f"Type: {type(arch_db)}")
    print(f"Content preview (last 800 chars):")
    if isinstance(arch_db, dict):
        content = arch_db.get('en_US', '')
    else:
        content = str(arch_db)
    print(content[-800:])
else:
    print("View not found")

cr.close()
