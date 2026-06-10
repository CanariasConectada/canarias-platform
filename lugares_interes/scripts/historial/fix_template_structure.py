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

# Get the website view
view = env["ir.ui.view"].browse(11527)
if view.exists():
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Parse the XML
    try:
        root = etree.fromstring(arch.encode())
        
        # Check if it's a template element
        if root.tag == 'template':
            print("Found template wrapper - extracting content")
            # Extract the inner content (t element)
            inner_content = []
            for child in root:
                inner_content.append(etree.tostring(child, encoding='unicode'))
            
            new_arch = ''.join(inner_content)
            
            # Update the view
            view.write({'arch_db': new_arch})
            env.cr.commit()
            print("Template structure fixed!")
            print(f"New arch length: {len(new_arch)}")
        else:
            print(f"Root tag is: {root.tag} - no fix needed")
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
else:
    print("View not found")

cr.close()
