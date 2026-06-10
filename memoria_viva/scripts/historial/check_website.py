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
    print(f"View website_id: {view.website_id}")
    print(f"View type: {view.type}")
    print(f"View mode: {view.mode}")
    
    # Check if there's a website-specific version
    website_id = 229  # Guanarteme website
    website_view = env["ir.ui.view"].search([
        ("key", "=", "memoria_viva.memoria_viva_detail"),
        ("website_id", "=", website_id)
    ])
    if website_view:
        print(f"Website-specific view found: ID {website_view.id}")
    else:
        print("No website-specific view found")
else:
    print("View not found")

cr.close()
