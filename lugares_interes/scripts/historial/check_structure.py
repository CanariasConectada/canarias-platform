#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

view = env["ir.ui.view"].search([("key", "=", "lugares_interes.lugares_interes_detail")])
if view:
    arch = view.arch_db
    if isinstance(arch, dict):
        arch = arch.get('en_US', '')
    
    # Buscar todas las etiquetas </template>
    count = arch.count('</template>')
    print(f"Found {count} </template> tags")
    
    # Mostrar las últimas 2000 caracteres para ver la estructura
    print("\nLast 2000 chars:")
    print(arch[-2000:])
else:
    print("View not found")

cr.close()
