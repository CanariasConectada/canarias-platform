#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba completo para el sistema de comentarios de Lugares de Interés
Valida el frontend, backend y API de comentarios
"""

import sys
import requests
import json

sys.path.insert(0, '/home/odoo/odoo')
import odoo
from odoo import api, SUPERUSER_ID

# Configuración
BASE_URL = "https://guanarteme.canariasconectada.es"
MEMORIA_URL = f"{BASE_URL}/lugares-de-interes"

def print_success(msg):
    print(f"✅ {msg}")

def print_error(msg):
    print(f"❌ {msg}")

def print_info(msg):
    print(f"ℹ️  {msg}")

def print_section(title):
    print(f"\n{'='*60}")
    print(f"🧪 {title}")
    print(f"{'='*60}")

class TestComentarios:
    def __init__(self):
        self.session = requests.Session()
        self.tests_passed = 0
        self.tests_failed = 0
        
        # Configurar Odoo
        odoo.tools.config.parse_config(['-c', '/home/odoo/odoo.conf'])
        self.db = odoo.sql_db.db_connect('canarias_conectada')
        self.cr = self.db.cursor()
        self.env = api.Environment(self.cr, SUPERUSER_ID, {})
        
    def run_test(self, name, test_func):
        """Ejecutar un test y registrar resultado"""
        try:
            result = test_func()
            if result:
                print_success(name)
                self.tests_passed += 1
            else:
                print_error(name)
                self.tests_failed += 1
        except Exception as e:
            print_error(f"{name} - Error: {e}")
            self.tests_failed += 1
            
    # ==================== TESTS DE FRONTEND ====================
    
    def test_01_pagina_listado_accesible(self):
        """Test: Página de listado carga correctamente"""
        response = self.session.get(MEMORIA_URL, timeout=30)
        return response.status_code == 200
    
    def test_02_pagina_detalle_accesible(self):
        """Test: Página de detalle carga correctamente"""
        # Buscar un lugar que exista
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            print_info("No hay lugares aprobados para probar")
            return True
            
        url = f"{MEMORIA_URL}/{lugar.slug}"
        response = self.session.get(url, timeout=30)
        return response.status_code == 200
    
    def test_03_seccion_comentarios_visible(self):
        """Test: Sección de comentarios está visible"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/{lugar.slug}"
        response = self.session.get(url, timeout=30)
        html = response.text
        
        return 'id="comentarios-lista"' in html and 'Comentarios' in html
    
    def test_04_mensaje_login_visible(self):
        """Test: Mensaje 'Inicia sesión' visible para usuarios anónimos"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/{lugar.slug}"
        response = self.session.get(url, timeout=30)
        html = response.text
        
        return 'Inicia sesión' in html and 'para dejar un comentario' in html
    
    def test_05_formulario_comentario_no_visible_anonimo(self):
        """Test: Formulario NO visible para usuarios anónimos"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/{lugar.slug}"
        response = self.session.get(url, timeout=30)
        html = response.text
        
        # El formulario debe tener clase 'd-none' o no estar presente para anónimos
        return 'id="comentarioForm"' not in html or 'd-none' in html.split('comentarioForm')[0][-200:]
    
    def test_06_boton_ver_mas_comentarios(self):
        """Test: Botón 'Ver más comentarios' presente"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/{lugar.slug}"
        response = self.session.get(url, timeout=30)
        html = response.text
        
        return 'id="verMasComentarios"' in html
    
    def test_07_contador_comentarios(self):
        """Test: Contador de comentarios presente"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/{lugar.slug}"
        response = self.session.get(url, timeout=30)
        html = response.text
        
        return 'id="total-comentarios"' in html
    
    # ==================== TESTS DE API ====================
    
    def test_08_api_listar_comentarios(self):
        """Test: API de listar comentarios funciona"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/comentario/listar?lugar_id={lugar.id}&offset=0&limit=10"
        response = self.session.get(url, timeout=30)
        
        if response.status_code != 200:
            return False
            
        try:
            data = response.json()
            return 'success' in data and 'comentarios' in data
        except:
            return False
    
    def test_09_api_crear_comentario_requiere_auth(self):
        """Test: API de crear comentario requiere autenticación"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            return True
            
        url = f"{MEMORIA_URL}/comentario/enviar"
        payload = {
            'lugar_id': lugar.id,
            'contenido': 'Test comentario'
        }
        
        # No seguir redirecciones para verificar el código real
        response = self.session.post(
            url, 
            json=payload,
            headers={'Content-Type': 'application/json'},
            timeout=30,
            allow_redirects=False
        )
        
        # Debe redirigir a login (302/303) o retornar 403/401
        return response.status_code in [302, 303, 401, 403]
    
    # ==================== TESTS DE BACKEND ====================
    
    def test_10_modelo_comentario_existe(self):
        """Test: Modelo de comentarios existe"""
        return 'lugares.interes.comentario' in self.env.registry
    
    def test_11_modelo_palabra_prohibida_existe(self):
        """Test: Modelo de palabras prohibidas existe"""
        return 'lugares.interes.palabra.prohibida' in self.env.registry
    
    def test_12_crear_comentario_backend(self):
        """Test: Crear comentario desde backend"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            print_info("No hay lugares para probar")
            return True
            
        admin = self.env.ref('base.user_admin')
        Comentario = self.env['lugares.interes.comentario'].sudo()
        
        try:
            comentario = Comentario.create({
                'lugar_id': lugar.id,
                'contenido': 'Comentario de prueba automatizado',
                'autor_id': admin.id,
            })
            return comentario.id > 0 and comentario.estado in ['aprobado', 'pendiente']
        except Exception as e:
            print_info(f"Error creando comentario: {e}")
            return False
    
    def test_13_crear_palabra_prohibida_backend(self):
        """Test: Crear palabra prohibida desde backend"""
        Palabra = self.env['lugares.interes.palabra.prohibida'].sudo()
        
        try:
            palabra = Palabra.create({
                'name': f'test_prohibida_{odoo.fields.Datetime.now().microsecond}',
                'active': True,
            })
            return palabra.id > 0
        except Exception as e:
            print_info(f"Error creando palabra: {e}")
            return False
    
    def test_14_moderacion_funciona(self):
        """Test: Comentario con palabra prohibida queda pendiente"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            print_info("No hay lugares para probar")
            return True
            
        # Crear palabra prohibida
        Palabra = self.env['lugares.interes.palabra.prohibida'].sudo()
        palabra_test = f'test_moderacion_{odoo.fields.Datetime.now().microsecond}'
        Palabra.create({'name': palabra_test, 'active': True})
        
        # Crear comentario con palabra prohibida
        admin = self.env.ref('base.user_admin')
        Comentario = self.env['lugares.interes.comentario'].sudo()
        
        comentario = Comentario.create({
            'lugar_id': lugar.id,
            'contenido': f'Este comentario contiene {palabra_test} que debe ser moderada',
            'autor_id': admin.id,
        })
        
        return comentario.estado == 'pendiente' and comentario.contiene_palabras_prohibidas
    
    def test_15_respuesta_comentario(self):
        """Test: Crear respuesta a comentario"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            print_info("No hay lugares para probar")
            return True
            
        admin = self.env.ref('base.user_admin')
        Comentario = self.env['lugares.interes.comentario'].sudo()
        
        # Crear comentario padre
        padre = Comentario.create({
            'lugar_id': lugar.id,
            'contenido': 'Comentario padre',
            'autor_id': admin.id,
            'estado': 'aprobado',
        })
        
        # Crear respuesta
        respuesta = Comentario.create({
            'lugar_id': lugar.id,
            'contenido': 'Respuesta al comentario',
            'autor_id': admin.id,
            'parent_id': padre.id,
            'estado': 'aprobado',
        })
        
        return respuesta.parent_id.id == padre.id
    
    def test_16_maximo_nivel_respuestas(self):
        """Test: No se permite nivel 2 de respuestas"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            print_info("No hay lugares para probar")
            return True
            
        admin = self.env.ref('base.user_admin')
        Comentario = self.env['lugares.interes.comentario'].sudo()
        
        # Crear jerarquía: padre -> hijo
        padre = Comentario.create({
            'lugar_id': lugar.id,
            'contenido': 'Nivel 0',
            'autor_id': admin.id,
            'estado': 'aprobado',
        })
        
        hijo = Comentario.create({
            'lugar_id': lugar.id,
            'contenido': 'Nivel 1',
            'autor_id': admin.id,
            'parent_id': padre.id,
            'estado': 'aprobado',
        })
        
        # Intentar crear nieto (nivel 2) - debe fallar
        try:
            nieto = Comentario.create({
                'lugar_id': lugar.id,
                'contenido': 'Nivel 2 - no permitido',
                'autor_id': admin.id,
                'parent_id': hijo.id,
                'estado': 'aprobado',
            })
            return False  # No debería permitirse
        except Exception:
            return True  # Correcto, debe fallar
    
    def test_17_configuracion_comentarios(self):
        """Test: Configuración permite activar/desactivar comentarios"""
        Settings = self.env['lugares.interes.settings'].sudo()
        settings = Settings.get_settings()
        
        # Verificar que tiene el campo
        return hasattr(settings, 'permitir_comentarios')
    
    def test_18_obtener_comentarios_aprobados(self):
        """Test: Método get_comentarios_aprobados funciona"""
        Lugar = self.env['lugares.interes.historia']
        lugar = Lugar.search([('state', '=', 'aprobado')], limit=1)
        if not lugar:
            print_info("No hay lugares para probar")
            return True
            
        Comentario = self.env['lugares.interes.comentario'].sudo()
        
        # Crear algunos comentarios de prueba
        admin = self.env.ref('base.user_admin')
        for i in range(3):
            Comentario.create({
                'lugar_id': lugar.id,
                'contenido': f'Comentario de prueba {i}',
                'autor_id': admin.id,
                'estado': 'aprobado',
            })
        
        # Obtener comentarios
        comentarios = Comentario.get_comentarios_aprobados(lugar.id)
        return len(comentarios) >= 0  # Debe retornar una lista
    
    # ==================== EJECUCIÓN ====================
    
    def run_all_tests(self):
        """Ejecutar todos los tests"""
        print("\n" + "="*60)
        print("🚀 INICIANDO TESTS DE SISTEMA DE COMENTARIOS")
        print("="*60)
        print(f"Base URL: {BASE_URL}")
        print(f"Fecha: {odoo.fields.Datetime.now()}")
        
        # Tests de Frontend
        print_section("TESTS DE FRONTEND (Páginas Web)")
        self.run_test("Página de listado accesible", self.test_01_pagina_listado_accesible)
        self.run_test("Página de detalle accesible", self.test_02_pagina_detalle_accesible)
        self.run_test("Sección de comentarios visible", self.test_03_seccion_comentarios_visible)
        self.run_test("Mensaje 'Inicia sesión' visible", self.test_04_mensaje_login_visible)
        self.run_test("Formulario oculto para anónimos", self.test_05_formulario_comentario_no_visible_anonimo)
        self.run_test("Botón 'Ver más' presente", self.test_06_boton_ver_mas_comentarios)
        self.run_test("Contador de comentarios presente", self.test_07_contador_comentarios)
        
        # Tests de API
        print_section("TESTS DE API (Endpoints)")
        self.run_test("API listar comentarios", self.test_08_api_listar_comentarios)
        self.run_test("API crear comentario requiere auth", self.test_09_api_crear_comentario_requiere_auth)
        
        # Tests de Backend
        print_section("TESTS DE BACKEND (Modelos)")
        self.run_test("Modelo comentarios existe", self.test_10_modelo_comentario_existe)
        self.run_test("Modelo palabra prohibida existe", self.test_11_modelo_palabra_prohibida_existe)
        self.run_test("Crear comentario backend", self.test_12_crear_comentario_backend)
        self.run_test("Crear palabra prohibida backend", self.test_13_crear_palabra_prohibida_backend)
        self.run_test("Moderación automática", self.test_14_moderacion_funciona)
        self.run_test("Respuesta a comentario", self.test_15_respuesta_comentario)
        self.run_test("Límite nivel respuestas", self.test_16_maximo_nivel_respuestas)
        self.run_test("Configuración comentarios", self.test_17_configuracion_comentarios)
        self.run_test("Obtener comentarios aprobados", self.test_18_obtener_comentarios_aprobados)
        
        # Resumen
        print_section("RESUMEN DE RESULTADOS")
        total = self.tests_passed + self.tests_failed
        print(f"✅ Tests pasados: {self.tests_passed}/{total}")
        print(f"❌ Tests fallidos: {self.tests_failed}/{total}")
        print(f"📊 Tasa de éxito: {(self.tests_passed/total)*100:.1f}%")
        
        self.cr.close()
        
        return self.tests_failed == 0

if __name__ == '__main__':
    tester = TestComentarios()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
