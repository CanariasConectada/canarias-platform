#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

with open("/home/odoo/addons/lugares_interes/views/lugares_interes_templates.xml", "r") as f:
    content = f.read()
    
# Verificar que el template existe en el archivo
if "lugares_interes_detail" in content:
    print("Template found in file")
    # Verificar si tiene la sección de comentarios
    if "comentarioForm" in content:
        print("Comentario form found in file")
    else:
        print("Comentario form NOT found in file")
else:
    print("Template NOT found in file")

# Verificar si el template está en la base de datos
view = env["ir.ui.view"].search([("key", "=", "lugares_interes.lugares_interes_detail")])
if view:
    print(f"Template in DB: ID {view.id}")
else:
    print("Template NOT in DB")
    # Intentar cargar el template manualmente
    try:
        # Leer el archivo XML
        from lxml import etree
        tree = etree.parse("/home/odoo/addons/lugares_interes/views/lugares_interes_templates.xml")
        root = tree.getroot()
        for template in root.findall(".//template"):
            template_id = template.get("id")
            if template_id == "lugares_interes_detail":
                print(f"Found template in XML: {template_id}")
                # Crear el view manualmente
                name = template.get("name", "Lugares de Interés - Detalle")
                arch = etree.tostring(template, encoding='unicode')
                view_vals = {
                    'name': name,
                    'key': f'lugares_interes.{template_id}',
                    'type': 'qweb',
                    'arch_db': arch,
                }
                new_view = env['ir.ui.view'].create(view_vals)
                print(f"Created view: ID {new_view.id}")
                env.cr.commit()
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

cr.close()
