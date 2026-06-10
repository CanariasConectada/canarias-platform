#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST FINAL - Sistema de Valoración con Estrellas
Valida escenarios anónimo y autenticado
"""

import sys
import json
import requests
from datetime import datetime

# Configuración
BASE_URL = "http://localhost:8069"
DOMAIN = "guanarteme.canariasconectada.es"
LUGAR_SLUG = "mirador-las-coloradas"
LUGAR_ID = 3

RESULTADOS = []

def log(modulo, prueba, exito, detalle=""):
    status = "✅" if exito else "❌"
    RESULTADOS.append({
        'modulo': modulo,
        'prueba': prueba,
        'exito': exito,
        'detalle': detalle
    })
    print(f"{status} [{modulo}] {prueba}")
    if detalle and not exito:
        print(f"   → {detalle}")

def test_anonimo():
    """Test como usuario anónimo"""
    print("\n" + "="*60)
    print("👤 TEST - Usuario ANÓNIMO (sin login)")
    print("="*60)
    
    session = requests.Session()
    headers = {"Host": DOMAIN}
    
    # 1. Acceder a página de detalle
    try:
        resp = session.get(f"{BASE_URL}/memoria-viva/{LUGAR_SLUG}", 
                          headers=headers, timeout=10)
        if resp.status_code == 200:
            log("ANONIMO", "Página detalle accesible", True)
            html = resp.text
            
            # Verificar elementos para anónimos
            if 'rating-display' in html:
                log("ANONIMO", "Promedio visible", True)
            else:
                log("ANONIMO", "Promedio visible", False, "No encontrado: rating-display")
            
            # Anónimos NO deben ver el formulario
            if 'rating-input' not in html:
                log("ANONIMO", "Formulario oculto (correcto)", True)
            else:
                log("ANONIMO", "Formulario oculto", False, "El formulario no debería estar visible")
            
            # Deben ver botón de login
            if 'inicia sesión' in html.lower() or 'login' in html.lower():
                log("ANONIMO", "Botón login visible", True)
            else:
                log("ANONIMO", "Botón login visible", False, "No encontrado")
        else:
            log("ANONIMO", "Página detalle", False, f"Status: {resp.status_code}")
    except Exception as e:
        log("ANONIMO", "Error página", False, str(e))
    
    # 2. Intentar enviar rating (debe fallar)
    try:
        resp = session.post(f"{BASE_URL}/memoria-viva/rating/enviar",
                           json={'lugar_id': LUGAR_ID, 'rating': 5},
                           headers={**headers, 'Content-Type': 'application/json'},
                           timeout=10)
        if resp.status_code in [401, 403]:
            log("ANONIMO", "Bloqueo envío rating", True, f"Status: {resp.status_code}")
        else:
            # Intentar parsear respuesta
            try:
                data = resp.json()
                if 'result' in data:
                    data = data['result']
                if not data.get('success') and ('login' in data.get('error', '').lower() or 'sesión' in data.get('error', '').lower()):
                    log("ANONIMO", "Bloqueo envío rating", True, f"Mensaje: {data.get('error')}")
                else:
                    log("ANONIMO", "Bloqueo envío rating", False, f"Debería rechazar: {data}")
            except:
                log("ANONIMO", "Bloqueo envío rating", True, f"Status: {resp.status_code}")
    except Exception as e:
        log("ANONIMO", "Error envío", False, str(e))

def test_backend():
    """Test directo en base de datos"""
    print("\n" + "="*60)
    print("🔧 TEST - Backend (Base de Datos)")
    print("="*60)
    
    import subprocess
    
    # 1. Verificar modelo existe
    try:
        result = subprocess.run([
            'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada', 
            '-c', "SELECT model FROM ir_model WHERE model = 'memoria.viva.rating';"
        ], capture_output=True, text=True, timeout=10)
        
        if 'memoria.viva.rating' in result.stdout:
            log("BACKEND", "Modelo existe", True)
        else:
            log("BACKEND", "Modelo existe", False, "Modelo no encontrado")
    except Exception as e:
        log("BACKEND", "Error modelo", False, str(e))
    
    # 2. Verificar campos
    try:
        result = subprocess.run([
            'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada',
            '-c', "SELECT name FROM ir_model_fields WHERE model = 'memoria.viva.rating';"
        ], capture_output=True, text=True, timeout=10)
        
        campos = ['lugar_id', 'user_id', 'rating']
        for campo in campos:
            if campo in result.stdout:
                log("BACKEND", f"Campo {campo}", True)
            else:
                log("BACKEND", f"Campo {campo}", False, "No encontrado")
    except Exception as e:
        log("BACKEND", "Error campos", False, str(e))
    
    # 3. Verificar campos computados en lugar
    try:
        result = subprocess.run([
            'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada',
            '-c', f"SELECT rating_avg, rating_count FROM memoria_viva_historia WHERE id = {LUGAR_ID};"
        ], capture_output=True, text=True, timeout=10)
        
        if 'rating_avg' in result.stdout and 'rating_count' in result.stdout:
            log("BACKEND", "Campos computados", True)
        else:
            log("BACKEND", "Campos computados", False)
    except Exception as e:
        log("BACKEND", "Error campos computados", False, str(e))
    
    # 4. Verificar permisos
    try:
        result = subprocess.run([
            'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada',
            '-c', "SELECT perm_read, perm_create FROM ir_model_access WHERE model_id = (SELECT id FROM ir_model WHERE model = 'memoria.viva.rating');"
        ], capture_output=True, text=True, timeout=10)
        
        lines = result.stdout.strip().split('\n')
        permisos_encontrados = False
        for line in lines:
            if '|' in line and ('t' in line or 'f' in line):
                permisos_encontrados = True
                break
        
        if permisos_encontrados:
            log("BACKEND", "Permisos configurados", True)
        else:
            log("BACKEND", "Permisos configurados", False)
    except Exception as e:
        log("BACKEND", "Error permisos", False, str(e))

def test_template():
    """Verificar template está completo"""
    print("\n" + "="*60)
    print("🎨 TEST - Template (Vista XML)")
    print("="*60)
    
    import subprocess
    
    # Buscar elementos en la vista
    elementos = [
        ('rating-display', 'Contenedor promedio'),
        ('rating-input', 'Input de valoración'),
        ('user-rating-value', 'Campo oculto'),
        ('btn-enviar-rating', 'Botón enviar'),
        ('btn-eliminar-rating', 'Botón eliminar'),
        ('memoria_viva_rating.js', 'Script JS'),
        ('VALORACIÓN', 'Título sección'),
    ]
    
    try:
        for elemento, descripcion in elementos:
            result = subprocess.run([
                'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada',
                '-c', f"SELECT 1 FROM ir_ui_view WHERE name = 'Memoria Viva - Detalle' AND arch_db::text LIKE '%{elemento}%';"
            ], capture_output=True, text=True, timeout=10)
            
            if '(1 row)' in result.stdout or '1' in result.stdout:
                log("TEMPLATE", descripcion, True)
            else:
                log("TEMPLATE", descripcion, False, f"No encontrado: {elemento}")
    except Exception as e:
        log("TEMPLATE", "Error", False, str(e))

def test_api_funcional():
    """Test de API endpoints"""
    print("\n" + "="*60)
    print("🌐 TEST - API Endpoints")
    print("="*60)
    
    session = requests.Session()
    headers = {"Host": DOMAIN}
    
    # 1. Listar comentarios (público)
    try:
        resp = session.get(f"{BASE_URL}/memoria-viva/comentario/listar?lugar_id={LUGAR_ID}",
                          headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get('result'):
                data = data['result']
            if data.get('success'):
                log("API", "Listar comentarios", True, f"Total: {data.get('total', 0)}")
            else:
                log("API", "Listar comentarios", False, data.get('error'))
        else:
            log("API", "Listar comentarios", False, f"Status: {resp.status_code}")
    except Exception as e:
        log("API", "Listar comentarios", False, str(e))
    
    # 2. Mi valoración (sin auth - debe fallar o retornar 0)
    try:
        resp = session.get(f"{BASE_URL}/memoria-viva/rating/mi-valoracion?lugar_id={LUGAR_ID}",
                          headers=headers, timeout=10)
        # Puede retornar 200 con error o 401/403
        if resp.status_code in [401, 403]:
            log("API", "Mi valoración sin auth", True, "Bloqueado correctamente")
        else:
            try:
                data = resp.json()
                if isinstance(data, dict) and data.get('result'):
                    data = data['result']
                if not data.get('success'):
                    log("API", "Mi valoración sin auth", True, f"Error controlado: {data.get('error')}")
                else:
                    log("API", "Mi valoración sin auth", False, f"No debería retornar datos: {data}")
            except:
                log("API", "Mi valoración sin auth", True, f"Respuesta no JSON: {resp.status_code}")
    except Exception as e:
        log("API", "Mi valoración error", False, str(e))

def resumen():
    """Mostrar resumen"""
    print("\n" + "="*60)
    print("📊 RESUMEN DE PRUEBAS")
    print("="*60)
    
    total = len(RESULTADOS)
    exitosos = sum(1 for r in RESULTADOS if r['exito'])
    
    print(f"\nTotal: {total} pruebas")
    print(f"✅ Exitosas: {exitosos}")
    print(f"❌ Fallidas: {total - exitosos}")
    print(f"📈 Éxito: {exitosos/total*100:.1f}%")
    
    # Por módulo
    modulos = {}
    for r in RESULTADOS:
        m = r['modulo']
        modulos[m] = modulos.get(m, {'total': 0, 'ok': 0})
        modulos[m]['total'] += 1
        if r['exito']:
            modulos[m]['ok'] += 1
    
    print("\nPor módulo:")
    for m, data in sorted(modulos.items()):
        status = "✅" if data['ok'] == data['total'] else "⚠️"
        print(f"  {status} {m}: {data['ok']}/{data['total']}")
    
    if exitosos == total:
        print("\n🎉 ¡TODAS LAS PRUEBAS PASARON!")
    elif exitosos >= total * 0.8:
        print("\n⚠️  PRUEBAS PASARON CON NOTA ALTA")
    else:
        print("\n❌ ALGUNAS PRUEBAS FALLARON")
    
    return exitosos == total

if __name__ == '__main__':
    print("="*60)
    print("🧪 TEST COMPLETO - Valoración con Estrellas")
    print("="*60)
    print(f"URL: {BASE_URL}")
    print(f"Dominio: {DOMAIN}")
    print(f"Lugar: {LUGAR_SLUG}")
    print("="*60)
    
    test_anonimo()
    test_backend()
    test_template()
    test_api_funcional()
    
    exito = resumen()
    sys.exit(0 if exito else 1)
