#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TEST - Filtros de ordenación y campo Año de Foto
Valida backend, frontend y API
"""

import sys
import requests

BASE_URL = "http://localhost:8069"
DOMAIN = "guanarteme.canariasconectada.es"
RESULTADOS = []

def log(modulo, prueba, exito, detalle=""):
    status = "✅" if exito else "❌"
    RESULTADOS.append({'modulo': modulo, 'prueba': prueba, 'exito': exito, 'detalle': detalle})
    print(f"{status} [{modulo}] {prueba}")
    if detalle and not exito:
        print(f"   → {detalle}")

def test_backend():
    """Test backend - Modelo y campos"""
    print("\n" + "="*60)
    print("🔧 TEST BACKEND")
    print("="*60)
    
    import subprocess
    
    # 1. Campo anio_foto existe
    try:
        result = subprocess.run([
            'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada', '-t', '-c',
            "SELECT 1 FROM ir_model_fields WHERE model = 'lugares.interes.historia' AND name = 'anio_foto';"
        ], capture_output=True, text=True, timeout=10)
        if '1' in result.stdout:
            log("BACKEND", "Campo anio_foto existe", True)
        else:
            log("BACKEND", "Campo anio_foto existe", False, "No encontrado")
    except Exception as e:
        log("BACKEND", "Error campo anio_foto", False, str(e))
    
    # 2. Validación constraint
    try:
        result = subprocess.run([
            'sudo', '-u', 'postgres', 'psql', '-d', 'canarias_conectada', '-t', '-c',
            "SELECT 1 FROM ir_model_constraint WHERE name LIKE '%check_anio_foto%';"
        ], capture_output=True, text=True, timeout=10)
        if '1' in result.stdout:
            log("BACKEND", "Constraint validación año", True)
        else:
            log("BACKEND", "Constraint validación año", False, "No encontrado")
    except Exception as e:
        log("BACKEND", "Error constraint", False, str(e))

def test_frontend():
    """Test frontend - Elementos visibles"""
    print("\n" + "="*60)
    print("🎨 TEST FRONTEND")
    print("="*60)
    
    session = requests.Session()
    headers = {"Host": DOMAIN}
    
    try:
        resp = session.get(f"{BASE_URL}/lugares-de-interes", headers=headers, timeout=10)
        html = resp.text
        
        checks = [
            ('dropdown', 'Dropdown ordenar existe'),
            ('Ordenar', 'Botón Ordenar visible'),
            ('Año', 'Botón Año visible'),
            ('fa-sort', 'Icono ordenar'),
            ('fa-calendar', 'Icono calendario'),
            ('valoracion', 'Opción valoración'),
            ('reacciones', 'Opción reacciones'),
            ('anio_foto', 'Campo año en datos'),
        ]
        
        for elemento, descripcion in checks:
            if elemento in html:
                log("FRONTEND", descripcion, True)
            else:
                log("FRONTEND", descripcion, False, f"No: {elemento}")
                
    except Exception as e:
        log("FRONTEND", "Error", False, str(e))

def test_api_ordenacion():
    """Test API - Ordenamiento"""
    print("\n" + "="*60)
    print("🌐 TEST API - Ordenación")
    print("="*60)
    
    session = requests.Session()
    headers = {"Host": DOMAIN}
    
    ordenes = ['valoracion', 'reacciones', 'antiguo', 'reciente']
    
    for orden in ordenes:
        try:
            resp = session.get(f"{BASE_URL}/lugares-de-interes?ordenar={orden}", 
                             headers=headers, timeout=10)
            if resp.status_code == 200:
                log("API", f"Ordenar por {orden}", True)
            else:
                log("API", f"Ordenar por {orden}", False, f"Status: {resp.status_code}")
        except Exception as e:
            log("API", f"Error orden {orden}", False, str(e))
    
    # Test filtro por año
    try:
        resp = session.get(f"{BASE_URL}/lugares-de-interes?anio=1980", 
                         headers=headers, timeout=10)
        if resp.status_code == 200:
            log("API", "Filtro por década 1980", True)
        else:
            log("API", "Filtro por década 1980", False, f"Status: {resp.status_code}")
    except Exception as e:
        log("API", "Error filtro año", False, str(e))

def test_tarjetas():
    """Test tarjetas - Badge de año"""
    print("\n" + "="*60)
    print("💳 TEST TARJETAS")
    print("="*60)
    
    session = requests.Session()
    headers = {"Host": DOMAIN}
    
    try:
        resp = session.get(f"{BASE_URL}/lugares-de-interes", headers=headers, timeout=10)
        html = resp.text
        
        if 'badge bg-info' in html and 'fa-calendar' in html:
            log("TARJETAS", "Badge año visible", True)
        else:
            log("TARJETAS", "Badge año visible", False, "No encontrado")
            
        if 'fa-heart' in html and 'fa-star' in html:
            log("TARJETAS", "Likes y rating visibles", True)
        else:
            log("TARJETAS", "Likes y rating visibles", False)
            
    except Exception as e:
        log("TARJETAS", "Error", False, str(e))

def test_formulario():
    """Test formulario - Campo año"""
    print("\n" + "="*60)
    print("📝 TEST FORMULARIO")
    print("="*60)
    
    session = requests.Session()
    headers = {"Host": DOMAIN}
    
    try:
        resp = session.get(f"{BASE_URL}/lugares-de-interes", headers=headers, timeout=10)
        html = resp.text
        
        checks = [
            ('name="anio_foto"', 'Input año existe'),
            ('min="1840"', 'Mínimo 1840'),
            ('max="2026"', 'Máximo 2026'),
            ('type="number"', 'Tipo número'),
            ('Año de la fotografía', 'Label año'),
        ]
        
        for elemento, descripcion in checks:
            if elemento in html:
                log("FORMULARIO", descripcion, True)
            else:
                log("FORMULARIO", descripcion, False, f"No: {elemento}")
                
    except Exception as e:
        log("FORMULARIO", "Error", False, str(e))

def resumen():
    """Resumen final"""
    print("\n" + "="*60)
    print("📊 RESUMEN")
    print("="*60)
    
    total = len(RESULTADOS)
    exitosos = sum(1 for r in RESULTADOS if r['exito'])
    
    print(f"Total: {total} | ✅ {exitosos} | ❌ {total - exitosos} | {exitosos/total*100:.0f}%")
    
    modulos = {}
    for r in RESULTADOS:
        m = r['modulo']
        modulos[m] = modulos.get(m, {'total': 0, 'ok': 0})
        modulos[m]['total'] += 1
        if r['exito']:
            modulos[m]['ok'] += 1
    
    print("\nPor módulo:")
    for m, d in sorted(modulos.items()):
        s = "✅" if d['ok'] == d['total'] else "⚠️"
        print(f"  {s} {m}: {d['ok']}/{d['total']}")
    
    return exitosos == total

if __name__ == '__main__':
    print("="*60)
    print("🧪 TEST - Filtros y Año de Foto")
    print("="*60)
    
    test_backend()
    test_frontend()
    test_api_ordenacion()
    test_tarjetas()
    test_formulario()
    
    exito = resumen()
    sys.exit(0 if exito else 1)
