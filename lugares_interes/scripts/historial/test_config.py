#!/usr/bin/env python3
import sys
sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
db = odoo.sql_db.db_connect('canarias_conectada')
cr = db.cursor()
env = api.Environment(cr, SUPERUSER_ID, {})

settings = env['lugares.interes.settings'].get_settings()
print(f"Tipo: {type(settings)}")
print(f"ID: {settings.id}")
print(f"permitir_comentarios: {settings.permitir_comentarios}")
print(f"Has attribute: {hasattr(settings, 'permitir_comentarios')}")

cr.close()
