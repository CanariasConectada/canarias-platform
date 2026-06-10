#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID
from lxml import etree

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

view = env["ir.ui.view"].search([("key", "=", "memoria_viva.memoria_viva_detail")])
if view:
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Parse XML
    root = etree.fromstring(arch.encode())
    
    # Find the comments section
    comments_row = root.xpath("//div[@class='row mt-5']")
    if comments_row:
        print(f"Found comments row: {len(comments_row)}")
        # Check parent
        for row in comments_row:
            parent = row.getparent()
            print(f"Parent tag: {parent.tag}")
            print(f"Parent class: {parent.get('class')}")
            # The comments should be inside the container, not outside
    else:
        print("Comments row not found")
else:
    print("View not found")

cr.close()
