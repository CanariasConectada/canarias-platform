#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

# Try to render the template manually
from odoo.addons.base.models.ir_qweb import QWeb

view = env["ir.ui.view"].search([("key", "=", "lugares_interes.lugares_interes_detail")])
if view:
    print(f"View found: ID {view.id}")
    
    # Get the arch
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Check if it has the comments section
    if 'comentarios-lista' in str(arch):
        print("Comments section found in arch")
    else:
        print("Comments section NOT found in arch")
        
    # Check for </template>
    if '</template>' in str(arch):
        print("Template end tag found")
        # Count occurrences
        count = str(arch).count('</template>')
        print(f"Template end tag count: {count}")
else:
    print("View not found")

cr.close()
