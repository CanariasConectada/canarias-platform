#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

# Get the actual rendered HTML
from odoo.http import request

# First, let's check if there's a website.page or something overriding
cr.execute("""
    SELECT v.id, v.name, v.key 
    FROM ir_ui_view v 
    WHERE v.key LIKE '%lugares_interes_detail%'
    OR v.inherit_id IN (SELECT id FROM ir_ui_view WHERE key = 'lugares_interes.lugares_interes_detail')
""")
views = cr.fetchall()
print("All related views:")
for v in views:
    print(f"  ID: {v[0]}, Name: {v[1]}, Key: {v[2]}")

cr.close()
