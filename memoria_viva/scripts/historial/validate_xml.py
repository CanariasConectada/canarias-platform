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
    
    print(f"View ID: {view.id}")
    print(f"Arch length: {len(arch)}")
    
    # Validate XML
    try:
        root = etree.fromstring(arch.encode())
        print("XML is valid")
        
        # Find the comments section
        comments_div = root.xpath("//div[@id='comentarios-lista']")
        if comments_div:
            print("Found comentarios-lista div")
        else:
            print("comentarios-lista div NOT found")
            
        # Find form
        form = root.xpath("//form[@id='comentarioForm']")
        if form:
            print("Found comentarioForm")
        else:
            print("comentarioForm NOT found")
            
    except etree.XMLSyntaxError as e:
        print(f"XML Error: {e}")
else:
    print("View not found")

cr.close()
