#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script para registrar manualmente los modelos de comentarios y palabras prohibidas
Ejecutar: python3 registrar_modelos.py
"""

import sys
sys.path.insert(0, '/home/odoo/odoo')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])

def main():
    db_name = 'canarias_conectada'
    
    try:
        db = odoo.sql_db.db_connect(db_name)
        cr = db.cursor()
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        print("Registrando modelos...")
        
        # Modelos a registrar
        modelos = [
            ('memoria.viva.comentario', 'Comentario - Memoria Viva'),
            ('memoria.viva.palabra.prohibida', 'Palabra Prohibida - Memoria Viva'),
        ]
        
        for model_name, description in modelos:
            # Verificar si ya existe
            existing = env['ir.model'].search([('model', '=', model_name)])
            if existing:
                print(f"  ✓ {model_name} ya existe (ID: {existing.id})")
                continue
            
            # Crear el modelo
            model_vals = {
                'model': model_name,
                'name': description,
                'state': 'manual',
                'transient': False,
            }
            model = env['ir.model'].create(model_vals)
            print(f"  ✓ {model_name} creado (ID: {model.id})")
            
            # Crear campo automático 'id'
            env['ir.model.fields'].create({
                'model_id': model.id,
                'name': 'id',
                'field_description': 'ID',
                'ttype': 'integer',
                'state': 'manual',
            })
            
            # Crear campo automático 'create_date'
            env['ir.model.fields'].create({
                'model_id': model.id,
                'name': 'create_date',
                'field_description': 'Created on',
                'ttype': 'datetime',
                'state': 'manual',
            })
            
            # Crear campo automático 'write_date'
            env['ir.model.fields'].create({
                'model_id': model.id,
                'name': 'write_date',
                'field_description': 'Last Updated on',
                'ttype': 'datetime',
                'state': 'manual',
            })
            
            # Crear campo automático 'create_uid'
            env['ir.model.fields'].create({
                'model_id': model.id,
                'name': 'create_uid',
                'field_description': 'Created by',
                'ttype': 'many2one',
                'relation': 'res.users',
                'state': 'manual',
            })
            
            # Crear campo automático 'write_uid'
            env['ir.model.fields'].create({
                'model_id': model.id,
                'name': 'write_uid',
                'field_description': 'Last Updated by',
                'ttype': 'many2one',
                'relation': 'res.users',
                'state': 'manual',
            })
        
        cr.commit()
        print("\n✓ Modelos registrados correctamente")
        print("\nNOTA: Reinicia Odoo para cargar las definiciones de campos desde los archivos Python.")
        
        cr.close()
        return True
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
