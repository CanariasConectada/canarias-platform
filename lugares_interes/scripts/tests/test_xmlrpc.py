#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prueba XML-RPC para el módulo Lugares de Interés
Ejecutar: python3 test_xmlrpc.py

Este script prueba todas las funcionalidades del módulo vía XML-RPC
tal como las usaría un cliente externo o aplicación móvil.
"""

import xmlrpc.client
import json
import sys
from datetime import datetime

# Configuración - Ajustar según el entorno
URL = 'http://localhost:8069'
DB = 'canarias_conectada'
USERNAME = 'admin'
PASSWORD = 'admin'

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


class LugaresInteresXmlRpcTest:
    """Clase de pruebas XML-RPC para Lugares de Interés"""
    
    def __init__(self, url, db, username, password):
        self.url = url
        self.db = db
        self.username = username
        self.password = password
        self.uid = None
        self.models = None
        self.website_id = None
        self.test_lugar_id = None
        
    def authenticate(self):
        """Autenticar con Odoo"""
        try:
            common = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/common')
            self.uid = common.authenticate(self.db, self.username, self.password, {})
            if self.uid:
                self.models = xmlrpc.client.ServerProxy(f'{self.url}/xmlrpc/2/object')
                print_success(f"Autenticación exitosa (UID: {self.uid})")
                return True
            else:
                print_error("Autenticación fallida")
                return False
        except Exception as e:
            print_error(f"Error de conexión: {e}")
            return False
    
    def call(self, model, method, *args):
        """Llamada genérica a modelos"""
        try:
            return self.models.execute_kw(
                self.db, self.uid, self.password,
                model, method, args
            )
        except Exception as e:
            print_error(f"Error en {model}.{method}: {e}")
            raise
    
    # === Tests de Lugares ===
    
    def test_01_crear_lugar(self):
        """Test: Crear un lugar histórico"""
        print_info("Test 01: Crear lugar histórico...")
        
        # Obtener website
        websites = self.call('website', 'search_read', [], ['id'], 1)
        if not websites:
            print_error("No hay website disponible")
            return False
        self.website_id = websites[0]['id']
        
        lugar_data = {
            'name': f'Lugar XML-RPC Test {datetime.now().strftime("%H%M%S")}',
            'description': 'Creado via XML-RPC',
            'website_primario_id': self.website_id,
            'website_ids': [(4, self.website_id)],
            'direccion': 'Calle XML-RPC 123',
            'publicador_nombre': 'Tester XML-RPC',
            'publicador_telefono': '123456789',
            'publicador_email': 'test@xmlrpc.com',
            'state': 'approved',
        }
        
        self.test_lugar_id = self.call('lugares.interes.historia', 'create', lugar_data)
        print_success(f"Lugar creado con ID: {self.test_lugar_id}")
        return True
    
    def test_02_leer_lugar(self):
        """Test: Leer datos de un lugar"""
        print_info("Test 02: Leer lugar...")
        
        lugar = self.call(
            'lugares.interes.historia', 'read',
            self.test_lugar_id,
            ['name', 'description', 'slug', 'state', 'view_count', 'like_count']
        )[0]
        
        print(f"  Nombre: {lugar['name']}")
        print(f"  Slug: {lugar['slug']}")
        print(f"  Estado: {lugar['state']}")
        print(f"  Vistas: {lugar['view_count']}")
        print(f"  Likes: {lugar['like_count']}")
        print_success("Lectura exitosa")
        return True
    
    def test_03_buscar_lugares(self):
        """Test: Buscar lugares aprobados"""
        print_info("Test 03: Buscar lugares...")
        
        lugares = self.call(
            'lugares.interes.historia', 'search_read',
            [('state', '=', 'approved')],
            ['name', 'slug', 'description', 'like_count'],
            0, 10
        )
        
        print(f"  Encontrados: {len(lugares)} lugares aprobados")
        for lugar in lugares[:3]:
            print(f"    - {lugar['name']} (Likes: {lugar['like_count']})")
        print_success("Búsqueda exitosa")
        return True
    
    def test_04_actualizar_lugar(self):
        """Test: Actualizar un lugar"""
        print_info("Test 04: Actualizar lugar...")
        
        self.call(
            'lugares.interes.historia', 'write',
            [self.test_lugar_id],
            {'description': 'Descripción actualizada via XML-RPC'}
        )
        
        lugar = self.call('lugares.interes.historia', 'read', self.test_lugar_id, ['description'])[0]
        print_success(f"Actualizado: {lugar['description']}")
        return True
    
    def test_05_incrementar_vistas(self):
        """Test: Incrementar contador de vistas"""
        print_info("Test 05: Incrementar vistas...")
        
        vistas_antes = self.call(
            'lugares.interes.historia', 'read',
            self.test_lugar_id, ['view_count']
        )[0]['view_count']
        
        self.call('lugares.interes.historia', 'incrementar_vistas', self.test_lugar_id)
        
        vistas_despues = self.call(
            'lugares.interes.historia', 'read',
            self.test_lugar_id, ['view_count']
        )[0]['view_count']
        
        print_success(f"Vistas: {vistas_antes} → {vistas_despues}")
        return True
    
    # === Tests de Likes ===
    
    def test_06_crear_like(self):
        """Test: Crear un like"""
        print_info("Test 06: Crear like...")
        
        like_data = {
            'lugar_id': self.test_lugar_id,
            'session_id': f'test-session-{datetime.now().strftime("%H%M%S")}',
        }
        
        like_id = self.call('lugares.interes.like', 'create', like_data)
        print_success(f"Like creado: ID {like_id}")
        
        # Verificar contador
        lugar = self.call('lugares.interes.historia', 'read', self.test_lugar_id, ['like_count'])[0]
        print(f"  Total likes: {lugar['like_count']}")
        return True
    
    def test_07_contar_likes(self):
        """Test: Contar likes de un lugar"""
        print_info("Test 07: Contar likes...")
        
        count = self.call(
            'lugares.interes.like', 'search_count',
            [('lugar_id', '=', self.test_lugar_id)]
        )
        print_success(f"Total likes: {count}")
        return True
    
    # === Tests de Comentarios ===
    
    def test_08_crear_comentario(self):
        """Test: Crear un comentario"""
        print_info("Test 08: Crear comentario...")
        
        comentario_data = {
            'lugar_id': self.test_lugar_id,
            'contenido': 'Comentario de prueba via XML-RPC',
            'autor_id': self.uid,
        }
        
        comentario_id = self.call('lugares.interes.comentario', 'create', comentario_data)
        print_success(f"Comentario creado: ID {comentario_id}")
        return True
    
    def test_09_listar_comentarios(self):
        """Test: Listar comentarios aprobados"""
        print_info("Test 09: Listar comentarios...")
        
        comentarios = self.call(
            'lugares.interes.comentario', 'get_comentarios_aprobados',
            self.test_lugar_id
        )
        
        print(f"  Encontrados: {len(comentarios)} comentarios")
        for c in comentarios:
            print(f"    - {c['autor_nombre']}: {c['contenido'][:50]}...")
        print_success("Listado exitoso")
        return True
    
    def test_10_buscar_comentarios(self):
        """Test: Buscar comentarios por estado"""
        print_info("Test 10: Buscar comentarios por estado...")
        
        for estado in ['aprobado', 'pendiente', 'rechazado']:
            count = self.call(
                'lugares.interes.comentario', 'search_count',
                [('estado', '=', estado)]
            )
            print(f"  {estado.capitalize()}: {count}")
        print_success("Búsqueda exitosa")
        return True
    
    def test_11_aprobar_comentario(self):
        """Test: Aprobar un comentario"""
        print_info("Test 11: Aprobar comentario...")
        
        # Crear comentario pendiente
        comentario_id = self.call('lugares.interes.comentario', 'create', {
            'lugar_id': self.test_lugar_id,
            'contenido': 'Comentario para aprobar',
            'autor_id': self.uid,
            'estado': 'pendiente',
        })
        
        # Aprobar
        self.call('lugares.interes.comentario', 'action_approve', [comentario_id])
        
        comentario = self.call(
            'lugares.interes.comentario', 'read',
            comentario_id, ['estado', 'moderado_por']
        )[0]
        
        print_success(f"Estado: {comentario['estado']}")
        return True
    
    def test_12_crear_respuesta(self):
        """Test: Crear respuesta a comentario"""
        print_info("Test 12: Crear respuesta...")
        
        # Crear comentario padre
        padre_id = self.call('lugares.interes.comentario', 'create', {
            'lugar_id': self.test_lugar_id,
            'contenido': 'Comentario padre',
            'autor_id': self.uid,
            'estado': 'aprobado',
        })
        
        # Crear respuesta
        respuesta_id = self.call('lugares.interes.comentario', 'create', {
            'lugar_id': self.test_lugar_id,
            'contenido': 'Respuesta al comentario',
            'autor_id': self.uid,
            'parent_id': padre_id,
            'estado': 'aprobado',
        })
        
        print_success(f"Respuesta creada: ID {respuesta_id}")
        return True
    
    # === Tests de Palabras Prohibidas ===
    
    def test_13_crear_palabra_prohibida(self):
        """Test: Crear palabra prohibida"""
        print_info("Test 13: Crear palabra prohibida...")
        
        palabra_data = {
            'name': f'palabra_test_{datetime.now().strftime("%H%M%S")}',
            'active': True,
        }
        
        palabra_id = self.call('lugares.interes.palabra.prohibida', 'create', palabra_data)
        print_success(f"Palabra prohibida creada: ID {palabra_id}")
        return True
    
    def test_14_listar_palabras_prohibidas(self):
        """Test: Listar palabras prohibidas activas"""
        print_info("Test 14: Listar palabras prohibidas...")
        
        palabras = self.call(
            'lugares.interes.palabra.prohibida', 'search_read',
            [('active', '=', True)],
            ['name'], 0, 10
        )
        
        print(f"  Activas: {len(palabras)}")
        for p in palabras:
            print(f"    - {p['name']}")
        print_success("Listado exitoso")
        return True
    
    # === Tests de Configuración ===
    
    def test_15_get_settings(self):
        """Test: Obtener configuración"""
        print_info("Test 15: Obtener configuración...")
        
        settings = self.call('lugares.interes.settings', 'get_settings', self.website_id)
        
        print(f"  Website ID: {settings.get('website_primario_id', 'N/A')}")
        print(f"  Comentarios permitidos: {settings['permitir_comentarios']}")
        print(f"  Moderación activa: {settings['moderar_comentarios']}")
        print_success("Configuración obtenida")
        return True
    
    def test_16_actualizar_settings(self):
        """Test: Actualizar configuración"""
        print_info("Test 16: Actualizar configuración...")
        
        # Buscar o crear configuración
        config_ids = self.call(
            'lugares.interes.settings', 'search',
            [('website_id', '=', self.website_id)]
        )
        
        if config_ids:
            self.call(
                'lugares.interes.settings', 'write',
                config_ids,
                {'permitir_comentarios': True, 'moderar_comentarios': True}
            )
            print_success("Configuración actualizada")
        else:
            print_info("No hay configuración existente para actualizar")
        return True
    
    # === Tests de Anuncios ===
    
    def test_17_crear_anuncio(self):
        """Test: Crear anuncio"""
        print_info("Test 17: Crear anuncio...")
        
        anuncio_data = {
            'name': f'Anuncio Test {datetime.now().strftime("%H%M%S")}',
            'tipo': 'banner',
            'titulo': 'Título del Anuncio',
            'subtitulo': 'Subtítulo',
            'descripcion': 'Descripción del anuncio',
            'website_primario_id': self.website_id,
            'website_ids': [(4, self.website_id)],
            'state': 'active',
        }
        
        anuncio_id = self.call('lugares.interes.anuncio', 'create', anuncio_data)
        print_success(f"Anuncio creado: ID {anuncio_id}")
        return True
    
    def test_18_listar_anuncios_activos(self):
        """Test: Listar anuncios activos"""
        print_info("Test 18: Listar anuncios activos...")
        
        anuncios = self.call(
            'lugares.interes.anuncio', 'search_read',
            [('state', '=', 'active')],
            ['name', 'titulo', 'tipo'], 0, 10
        )
        
        print(f"  Activos: {len(anuncios)}")
        for a in anuncios:
            print(f"    - [{a['tipo']}] {a['titulo']}")
        print_success("Listado exitoso")
        return True
    
    # === Tests de Tipos y Categorías ===
    
    def test_19_listar_tipos(self):
        """Test: Listar tipos de lugares"""
        print_info("Test 19: Listar tipos...")
        
        tipos = self.call(
            'lugares.interes.tipo', 'search_read',
            [], ['name', 'active'], 0, 20
        )
        
        print(f"  Total tipos: {len(tipos)}")
        print_success("Tipos listados")
        return True
    
    def test_20_listar_categorias(self):
        """Test: Listar categorías"""
        print_info("Test 20: Listar categorías...")
        
        categorias = self.call(
            'lugares.interes.categoria', 'search_read',
            [], ['name', 'active'], 0, 20
        )
        
        print(f"  Total categorías: {len(categorias)}")
        print_success("Categorías listadas")
        return True
    
    # === Limpieza ===
    
    def cleanup(self):
        """Limpiar datos de prueba"""
        print_info("Limpiando datos de prueba...")
        try:
            if self.test_lugar_id:
                self.call('lugares.interes.historia', 'unlink', [self.test_lugar_id])
                print_success("Datos de prueba eliminados")
        except Exception as e:
            print_error(f"Error en limpieza: {e}")
    
    # === Ejecución ===
    
    def run_all_tests(self):
        """Ejecutar todos los tests"""
        print("=" * 60)
        print("MEMORIA VIVA - PRUEBAS XML-RPC")
        print("=" * 60)
        print(f"URL: {self.url}")
        print(f"Base de datos: {self.db}")
        print(f"Usuario: {self.username}")
        print("=" * 60)
        
        if not self.authenticate():
            return False
        
        tests = [
            # Lugares
            ("Crear Lugar", self.test_01_crear_lugar),
            ("Leer Lugar", self.test_02_leer_lugar),
            ("Buscar Lugares", self.test_03_buscar_lugares),
            ("Actualizar Lugar", self.test_04_actualizar_lugar),
            ("Incrementar Vistas", self.test_05_incrementar_vistas),
            # Likes
            ("Crear Like", self.test_06_crear_like),
            ("Contar Likes", self.test_07_contar_likes),
            # Comentarios
            ("Crear Comentario", self.test_08_crear_comentario),
            ("Listar Comentarios", self.test_09_listar_comentarios),
            ("Buscar Comentarios", self.test_10_buscar_comentarios),
            ("Aprobar Comentario", self.test_11_aprobar_comentario),
            ("Crear Respuesta", self.test_12_crear_respuesta),
            # Moderación
            ("Crear Palabra Prohibida", self.test_13_crear_palabra_prohibida),
            ("Listar Palabras Prohibidas", self.test_14_listar_palabras_prohibidas),
            # Configuración
            ("Obtener Settings", self.test_15_get_settings),
            ("Actualizar Settings", self.test_16_actualizar_settings),
            # Anuncios
            ("Crear Anuncio", self.test_17_crear_anuncio),
            ("Listar Anuncios", self.test_18_listar_anuncios_activos),
            # Tipos/Categorías
            ("Listar Tipos", self.test_19_listar_tipos),
            ("Listar Categorías", self.test_20_listar_categorias),
        ]
        
        passed = 0
        failed = 0
        
        for name, test_func in tests:
            print()
            try:
                if test_func():
                    passed += 1
                else:
                    failed += 1
            except Exception as e:
                print_error(f"{name}: {e}")
                failed += 1
        
        print()
        print("=" * 60)
        print(f"RESULTADOS: {passed} pasados, {failed} fallidos")
        print("=" * 60)
        
        # Limpieza
        self.cleanup()
        
        return failed == 0


def main():
    """Función principal"""
    # Permitir configuración via argumentos
    url = sys.argv[1] if len(sys.argv) > 1 else URL
    db = sys.argv[2] if len(sys.argv) > 2 else DB
    username = sys.argv[3] if len(sys.argv) > 3 else USERNAME
    password = sys.argv[4] if len(sys.argv) > 4 else PASSWORD
    
    tester = LugaresInteresXmlRpcTest(url, db, username, password)
    success = tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
