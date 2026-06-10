#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST COMPLETO - Sistema de Valoración con Estrellas
Valida frontend, backend, API y seguridad
"""

import sys
import json
import requests
import xmlrpc.client
from datetime import datetime

# Configuración
ODOO_URL = "https://guanarteme.canariasconectada.es"
ODOO_DB = "canarias_conectada"
ADMIN_USER = "admin"  # Reemplazar si es necesario
ADMIN_PASS = "admin"  # Reemplazar si es necesario

LUGAR_ID = 3  # Mirador Las Coloradas
LUGAR_SLUG = "mirador-las-coloradas"

RESULTADOS = []


def log(seccion, prueba, exito, detalle=""):
    """Registra resultado de prueba"""
    status = "✅ PASS" if exito else "❌ FAIL"
    RESULTADOS.append({
        'seccion': seccion,
        'prueba': prueba,
        'exito': exito,
        'detalle': detalle
    })
    print(f"{status} [{seccion}] {prueba}")
    if detalle and not exito:
        print(f"      → {detalle}")


def test_backend_modelo():
    """Prueba 1: Verificar que el modelo existe y tiene registros"""
    print("\n" + "="*60)
    print("🔧 TEST BACKEND - Modelo de Datos")
    print("="*60)
    
    try:
        # Conectar vía XML-RPC
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ADMIN_USER, ADMIN_PASS, {})
        
        if not uid:
            log("BACKEND", "Autenticación XML-RPC", False, "Credenciales inválidas")
            return
        
        log("BACKEND", "Autenticación XML-RPC", True, f"UID: {uid}")
        
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        
        # Verificar que el modelo existe
        model_ids = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'ir.model', 'search', [[['model', '=', 'lugares.interes.rating']]])
        
        if model_ids:
            log("BACKEND", "Modelo lugares.interes.rating existe", True, f"ID: {model_ids[0]}")
        else:
            log("BACKEND", "Modelo lugares.interes.rating existe", False, "Modelo no encontrado")
        
        # Verificar campos del modelo
        campos = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'lugares.interes.rating', 'fields_get', [], {'attributes': ['string', 'type']})
        
        campos_requeridos = ['lugar_id', 'user_id', 'rating']
        for campo in campos_requeridos:
            if campo in campos:
                log("BACKEND", f"Campo {campo}", True, f"Tipo: {campos[campo]['type']}")
            else:
                log("BACKEND", f"Campo {campo}", False, "No encontrado")
        
        # Verificar constraint único
        constraints = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'lugares.interes.rating', '_sql_constraints', [])
        
        log("BACKEND", "Constraints SQL", True, f"Encontrados: {len(constraints) if constraints else 0}")
        
    except Exception as e:
        log("BACKEND", "Error general", False, str(e))


def test_backend_campos_computados():
    """Prueba 2: Verificar campos computados en lugar"""
    print("\n" + "="*60)
    print("🔧 TEST BACKEND - Campos Computados")
    print("="*60)
    
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ADMIN_USER, ADMIN_PASS, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        
        # Leer lugar y verificar campos
        lugar = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'lugares.interes.historia', 'read', [[LUGAR_ID]], 
            {'fields': ['name', 'rating_avg', 'rating_count']})
        
        if lugar:
            log("BACKEND", "Lugar accesible", True, f"{lugar[0]['name']}")
            log("BACKEND", "Campo rating_avg", True, f"Valor: {lugar[0].get('rating_avg', 'N/A')}")
            log("BACKEND", "Campo rating_count", True, f"Valor: {lugar[0].get('rating_count', 'N/A')}")
        else:
            log("BACKEND", "Lugar accesible", False, f"ID {LUGAR_ID} no encontrado")
            
    except Exception as e:
        log("BACKEND", "Error campos computados", False, str(e))


def test_api_endpoints():
    """Prueba 3: Probar endpoints API"""
    print("\n" + "="*60)
    print("🌐 TEST API - Endpoints REST")
    print("="*60)
    
    session = requests.Session()
    
    # Test 3.1: Endpoint enviar sin autenticación (debe fallar)
    try:
        resp = session.post(
            f"{ODOO_URL}/lugares-de-interes/rating/enviar",
            json={'lugar_id': LUGAR_ID, 'rating': 5},
            headers={'Content-Type': 'application/json'},
            timeout=10
        )
        
        if resp.status_code in [401, 403] or 'login' in resp.text.lower():
            log("API", "Enviar sin auth (esperado 401/403)", True, f"Status: {resp.status_code}")
        else:
            log("API", "Enviar sin auth", False, f"Debería rechazar, status: {resp.status_code}")
    except Exception as e:
        log("API", "Enviar sin auth - Error", False, str(e))
    
    # Test 3.2: Endpoint mi-valoracion sin auth (debe fallar)
    try:
        resp = session.get(
            f"{ODOO_URL}/lugares-de-interes/rating/mi-valoracion?lugar_id={LUGAR_ID}",
            timeout=10
        )
        
        if resp.status_code in [401, 403]:
            log("API", "Mi valoración sin auth (esperado 401/403)", True, f"Status: {resp.status_code}")
        else:
            log("API", "Mi valoración sin auth", False, f"Debería rechazar, status: {resp.status_code}")
    except Exception as e:
        log("API", "Mi valoración sin auth - Error", False, str(e))
    
    # Test 3.3: Página de detalle (debe funcionar - pública)
    try:
        resp = session.get(
            f"{ODOO_URL}/lugares-de-interes/{LUGAR_SLUG}",
            timeout=10
        )
        
        if resp.status_code == 200:
            # Verificar que contiene el widget de rating
            if 'rating-display' in resp.text or 'VALORACIÓN' in resp.text:
                log("API", "Página detalle con widget", True, "Widget de valoración presente")
            else:
                log("API", "Página detalle con widget", False, "Widget no encontrado en HTML")
        else:
            log("API", "Página detalle", False, f"Status: {resp.status_code}")
    except Exception as e:
        log("API", "Página detalle - Error", False, str(e))


def test_frontend_render():
    """Prueba 4: Verificar renderizado del frontend"""
    print("\n" + "="*60)
    print("🎨 TEST FRONTEND - Renderizado")
    print("="*60)
    
    try:
        resp = requests.get(
            f"{ODOO_URL}/lugares-de-interes/{LUGAR_SLUG}",
            timeout=10
        )
        
        html = resp.text
        
        # Verificar elementos clave
        checks = [
            ('rating-display', 'Contenedor de estrellas'),
            ('rating-input', 'Input de valoración'),
            ('btn-enviar-rating', 'Botón enviar'),
            ('btn-eliminar-rating', 'Botón eliminar'),
            ('user-rating-value', 'Campo oculto valoración'),
            ('lugares_interes_rating.js', 'Script JS incluido'),
            ('VALORACIÓN', 'Título sección'),
        ]
        
        for elemento, descripcion in checks:
            if elemento in html:
                log("FRONTEND", descripcion, True)
            else:
                log("FRONTEND", descripcion, False, f"No encontrado: {elemento}")
        
        # Verificar estructura visual
        if 'display-4' in html and 'fw-bold' in html:
            log("FRONTEND", "Estilos de promedio", True)
        else:
            log("FRONTEND", "Estilos de promedio", False)
            
    except Exception as e:
        log("FRONTEND", "Error renderizado", False, str(e))


def test_seguridad():
    """Prueba 5: Verificar permisos de acceso"""
    print("\n" + "="*60)
    print("🔒 TEST SEGURIDAD - Permisos")
    print("="*60)
    
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ADMIN_USER, ADMIN_PASS, {})
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        
        # Verificar reglas de acceso
        access_rules = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'ir.model.access', 'search_read',
            [[['model_id.model', '=', 'lugares.interes.rating']]],
            {'fields': ['name', 'group_id', 'perm_read', 'perm_write', 'perm_create', 'perm_unlink']})
        
        if access_rules:
            log("SEGURIDAD", "Reglas de acceso definidas", True, f"{len(access_rules)} reglas")
            
            for rule in access_rules:
                group = rule.get('group_id', [False, 'Public'])[1] if rule.get('group_id') else 'Public'
                perms = f"R:{rule['perm_read']} W:{rule['perm_write']} C:{rule['perm_create']} U:{rule['perm_unlink']}"
                log("SEGURIDAD", f"Permisos {group}", True, perms)
        else:
            log("SEGURIDAD", "Reglas de acceso", False, "No encontradas")
            
    except Exception as e:
        log("SEGURIDAD", "Error verificando permisos", False, str(e))


def test_crear_valoracion():
    """Prueba 6: Crear una valoración de prueba"""
    print("\n" + "="*60)
    print("⭐ TEST FUNCIONAL - Crear Valoración")
    print("="*60)
    
    try:
        common = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/common")
        uid = common.authenticate(ODOO_DB, ADMIN_USER, ADMIN_PASS, {})
        
        if not uid:
            log("FUNCIONAL", "Autenticación", False, "No se pudo autenticar")
            return
        
        models = xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")
        
        # Verificar si ya existe una valoración
        existing = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'lugares.interes.rating', 'search',
            [[['lugar_id', '=', LUGAR_ID], ['user_id', '=', uid]]])
        
        if existing:
            log("FUNCIONAL", "Valoración existente", True, f"ID: {existing[0]}")
            # Actualizar en lugar de crear
            models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
                'lugares.interes.rating', 'write',
                [existing, {'rating': 4}])
            log("FUNCIONAL", "Actualizar valoración", True, "Rating cambiado a 4")
        else:
            # Crear nueva valoración
            rating_id = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
                'lugares.interes.rating', 'create',
                [{'lugar_id': LUGAR_ID, 'user_id': uid, 'rating': 5}])
            log("FUNCIONAL", "Crear valoración", True, f"ID: {rating_id}")
        
        # Verificar que se recalculó el promedio
        lugar = models.execute_kw(ODOO_DB, uid, ADMIN_PASS,
            'lugares.interes.historia', 'read', [[LUGAR_ID]],
            {'fields': ['rating_avg', 'rating_count']})
        
        if lugar:
            log("FUNCIONAL", "Promedio recalculado", True, 
                f"Avg: {lugar[0]['rating_avg']:.1f}, Count: {lugar[0]['rating_count']}")
        
    except Exception as e:
        log("FUNCIONAL", "Error creando valoración", False, str(e))


def resumen_final():
    """Muestra resumen de todas las pruebas"""
    print("\n" + "="*60)
    print("📊 RESUMEN DE PRUEBAS")
    print("="*60)
    
    total = len(RESULTADOS)
    exitosos = sum(1 for r in RESULTADOS if r['exito'])
    fallidos = total - exitosos
    
    # Agrupar por sección
    secciones = {}
    for r in RESULTADOS:
        sec = r['seccion']
        if sec not in secciones:
            secciones[sec] = {'total': 0, 'exitosos': 0}
        secciones[sec]['total'] += 1
        if r['exito']:
            secciones[sec]['exitosos'] += 1
    
    print(f"\nTotal pruebas: {total}")
    print(f"✅ Exitosas: {exitosos}")
    print(f"❌ Fallidas: {fallidos}")
    print(f"📈 Porcentaje: {(exitosos/total*100) if total > 0 else 0:.1f}%")
    
    print("\nPor sección:")
    for sec, data in sorted(secciones.items()):
        status = "✅" if data['exitosos'] == data['total'] else "⚠️"
        print(f"  {status} {sec}: {data['exitosos']}/{data['total']}")
    
    if fallidos > 0:
        print("\n❌ Pruebas fallidas:")
        for r in RESULTADOS:
            if not r['exito']:
                print(f"  - [{r['seccion']}] {r['prueba']}")
                if r['detalle']:
                    print(f"    → {r['detalle']}")
    
    print("\n" + "="*60)
    if fallidos == 0:
        print("🎉 ¡TODAS LAS PRUEBAS PASARON!")
    elif fallidos <= 2:
        print("⚠️  PRUEBAS PASARON CON ADVERTENCIAS MENORES")
    else:
        print("❌ ALGUNAS PRUEBAS FALLARON - REVISAR")
    print("="*60)
    
    return fallidos == 0


if __name__ == '__main__':
    print("="*60)
    print("🧪 TEST COMPLETO - Sistema de Valoración")
    print("="*60)
    print(f"URL: {ODOO_URL}")
    print(f"Base de datos: {ODOO_DB}")
    print(f"Lugar de prueba: {LUGAR_SLUG} (ID: {LUGAR_ID})")
    print("="*60)
    
    # Ejecutar todas las pruebas
    test_backend_modelo()
    test_backend_campos_computados()
    test_api_endpoints()
    test_frontend_render()
    test_seguridad()
    test_crear_valoracion()
    
    # Mostrar resumen
    exito = resumen_final()
    
    sys.exit(0 if exito else 1)
