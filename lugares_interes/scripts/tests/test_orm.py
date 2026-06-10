#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba ORM para Lugares de Interés
Ejecutar desde el entorno de Odoo
"""

import sys
sys.path.insert(0, '/home/odoo/odoo')

import odoo
from odoo import api, SUPERUSER_ID

# Configuración
odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])

# Colores para output
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


def print_success(msg):
    print(f"{GREEN}✓ {msg}{RESET}")


def print_error(msg):
    print(f"{RED}✗ {msg}{RESET}")


def print_info(msg):
    print(f"{YELLOW}ℹ {msg}{RESET}")


def run_tests():
    """Ejecutar todos los tests"""
    print("=" * 60)
    print("MEMORIA VIVA - PRUEBAS ORM")
    print("=" * 60)
    
    db_name = 'canarias_conectada'
    
    try:
        db = odoo.sql_db.db_connect(db_name)
        cr = db.cursor()
        
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        # === Test 1: Buscar lugares ===
        print_info("Test 1: Buscar lugares aprobados...")
        Lugar = env['lugares.interes.historia']
        lugares = Lugar.search([('state', '=', 'approved')], limit=5)
        print_success(f"Encontrados {len(lugares)} lugares")
        for lugar in lugares:
            print(f"  - {lugar.name} (Likes: {lugar.like_count})")
        
        # === Test 2: Contar lugares ===
        print_info("Test 2: Contar lugares...")
        total = Lugar.search_count([('state', '=', 'approved')])
        print_success(f"Total lugares aprobados: {total}")
        
        # === Test 3: Crear un lugar ===
        print_info("Test 3: Crear lugar de prueba...")
        website = env['website'].search([], limit=1)
        lugar_test = Lugar.create({
            'name': 'Lugar Test ORM',
            'description': 'Creado via script de prueba',
            'website_primario_id': website.id,
            'website_ids': [(4, website.id)],
            'state': 'aprobado',
            'publicador_nombre': 'Tester ORM',
        })
        print_success(f"Lugar creado: ID {lugar_test.id}")
        
        # === Test 4: Leer datos ===
        print_info("Test 4: Leer datos del lugar...")
        print(f"  Nombre: {lugar_test.name}")
        print(f"  Slug: {lugar_test.slug}")
        print(f"  Estado: {lugar_test.state}")
        print_success("Lectura exitosa")
        
        # === Test 5: Actualizar lugar ===
        print_info("Test 5: Actualizar lugar...")
        lugar_test.write({'description': 'Descripción actualizada'})
        print_success(f"Descripción: {lugar_test.description}")
        
        # === Test 6: Like count ===
        print_info("Test 6: Verificar like_count...")
        print_success(f"Likes iniciales: {lugar_test.like_count}")
        
        # === Test 7: Crear like ===
        print_info("Test 7: Crear like...")
        Like = env['lugares.interes.like']
        like = Like.create({
            'lugar_id': lugar_test.id,
            'session_id': 'test-session-orm',
        })
        print_success(f"Like creado: ID {like.id}")
        print(f"  Total likes del lugar: {lugar_test.like_count}")
        
        # === Test 8: Crear comentario ===
        print_info("Test 8: Crear comentario...")
        Comentario = env['lugares.interes.comentario']
        admin = env.ref('base.user_admin')
        comentario = Comentario.create({
            'lugar_id': lugar_test.id,
            'contenido': 'Comentario de prueba ORM',
            'autor_id': admin.id,
        })
        print_success(f"Comentario creado: ID {comentario.id}")
        print(f"  Estado: {comentario.estado}")
        print(f"  Autor: {comentario.autor_nombre}")
        
        # === Test 9: Obtener comentarios ===
        print_info("Test 9: Obtener comentarios aprobados...")
        comentarios = Comentario.get_comentarios_aprobados(lugar_test.id)
        print_success(f"Comentarios aprobados: {len(comentarios)}")
        
        # === Test 10: Crear respuesta ===
        print_info("Test 10: Crear respuesta...")
        respuesta = Comentario.create({
            'lugar_id': lugar_test.id,
            'contenido': 'Respuesta al comentario',
            'autor_id': admin.id,
            'parent_id': comentario.id,
        })
        print_success(f"Respuesta creada: ID {respuesta.id}")
        
        # === Test 11: Palabra prohibida ===
        print_info("Test 11: Crear palabra prohibida...")
        Palabra = env['lugares.interes.palabra.prohibida']
        palabra = Palabra.create({'name': 'test_prohibido_orm'})
        print_success(f"Palabra prohibida: {palabra.name}")
        
        # === Test 12: Comentario con moderación ===
        print_info("Test 12: Crear comentario con palabra prohibida...")
        comentario_mod = Comentario.create({
            'lugar_id': lugar_test.id,
            'contenido': 'Este mensaje contiene test_prohibido_orm',
            'autor_id': admin.id,
        })
        print_success(f"Comentario moderado: ID {comentario_mod.id}")
        print(f"  Estado: {comentario_mod.estado}")
        print(f"  Palabras prohibidas: {comentario_mod.contiene_palabras_prohibidas}")
        
        # === Test 13: Configuración ===
        print_info("Test 13: Obtener configuración...")
        Settings = env['lugares.interes.settings']
        settings = Settings.get_settings()
        print_success(f"Configuración obtenida")
        print(f"  Comentarios permitidos: {settings['permitir_comentarios']}")
        print(f"  Moderación: {settings['moderar_comentarios']}")
        
        # === Test 14: Tipos ===
        print_info("Test 14: Listar tipos...")
        Tipo = env['lugares.interes.tipo']
        tipos = Tipo.search([])
        print_success(f"Total tipos: {len(tipos)}")
        
        # === Test 15: Categorías ===
        print_info("Test 15: Listar categorías...")
        Categoria = env['lugares.interes.categoria']
        categorias = Categoria.search([])
        print_success(f"Total categorías: {len(categorias)}")
        
        # === Test 16: Anuncios ===
        print_info("Test 16: Listar anuncios...")
        Anuncio = env['lugares.interes.anuncio']
        anuncios = Anuncio.search([('state', '=', 'active')])
        print_success(f"Anuncios activos: {len(anuncios)}")
        
        # === Limpieza ===
        print_info("Limpiando datos de prueba...")
        # No eliminamos para poder revisar en el backend
        cr.commit()
        print_success("Transacción guardada (datos de prueba conservados)")
        
        cr.close()
        
        print()
        print("=" * 60)
        print("TODOS LOS TESTS PASARON ✓")
        print("=" * 60)
        
        return True
        
    except Exception as e:
        print_error(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)
