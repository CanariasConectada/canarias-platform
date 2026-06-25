# -*- coding: utf-8 -*-
"""
Tests para modelos del módulo Memoria Viva
"""
from odoo.tests import common, tagged
from odoo.exceptions import AccessError, ValidationError
from odoo.tools import mute_logger


@tagged('post_install', '-at_install')
class TestMemoriaVivaModels(common.TransactionCase):
    """Tests para modelos de Memoria Viva"""
    
    @classmethod
    def setUpClass(cls):
        super(TestMemoriaVivaModels, cls).setUpClass()
        
        # Crear usuarios de prueba
        cls.user_admin = cls.env.ref('base.user_admin')
        # base.user_demo no existe en BD sin datos demo: creamos un usuario
        # interno básico (sin privilegios de aprobador) equivalente.
        cls.user_demo = cls.env['res.users'].create({
            'name': 'Test Demo User',
            'login': 'mv_test_demo_models',
            'email': 'mv_test_demo_models@example.com',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        
        # Crear grupo de aprobadores
        cls.group_approver = cls.env['res.groups'].create({
            'name': 'Memoria Viva - Aprobador',
            'implied_ids': [(4, cls.env.ref('base.group_user').id)],
        })
        
        cls.user_approver = cls.env['res.users'].create({
            'name': 'Test Approver',
            'login': 'test_approver',
            'groups_id': [(4, cls.group_approver.id)],
        })
        
        # Crear website para pruebas
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
                'domain': 'test.local',
            })
        
        # Crear tipo de lugar
        cls.tipo = cls.env['memoria.viva.tipo'].create({
            'name': 'Monumento Histórico',
        })
        
        # Crear categoría
        cls.categoria = cls.env['memoria.viva.categoria'].create({
            'name': 'Arquitectura',
        })
        
        # Crear un lugar de prueba
        cls.lugar = cls.env['memoria.viva.historia'].create({
            'name': 'Plaza Mayor Test',
            'description': 'Una plaza histórica de test',
            'tipo_id': cls.tipo.id,
            'categoria_id': cls.categoria.id,
            'direccion': 'Calle Test 123',
            'latitude': 28.1234,
            'longitude': -15.5678,
            'website_primario_id': cls.website.id,
            'state': 'aprobado',
            'publicador_nombre': 'Test Publisher',
            'publicador_telefono': '123456789',
            'publicador_email': 'test@example.com',
        })

        # Configuración: ahora son campos website-specific (memoria_viva_*)
        # editados vía res.config.settings (el modelo memoria.viva.settings
        # ya no existe).
        cls.website.write({
            'memoria_viva_permitir_comentarios': True,
            'memoria_viva_show_tipo': True,
            'memoria_viva_show_categoria': True,
            'memoria_viva_show_descripcion_larga': True,
            'memoria_viva_show_coordenadas': True,
        })
    
    # === Tests de MemoriaVivaHistoria ===
    
    def test_01_crear_lugar(self):
        """Test: Crear un lugar histórico"""
        lugar = self.env['memoria.viva.historia'].create({
            'name': 'Nuevo Lugar Test',
            'description': 'Descripción de test',
            'tipo_id': self.tipo.id,
            'website_primario_id': self.website.id,
            'state': 'pendiente',
        })
        self.assertTrue(lugar.id)
        self.assertEqual(lugar.name, 'Nuevo Lugar Test')
        self.assertEqual(lugar.state, 'pendiente')
        self.assertTrue(lugar.slug)
        self.assertIn('nuevo-lugar-test', lugar.slug)
    
    def test_02_slug_unico(self):
        """Test: El slug debe ser único"""
        lugar1 = self.env['memoria.viva.historia'].create({
            'name': 'Lugar Único',
            'description': 'Test',
            'website_primario_id': self.website.id,
        })
        lugar2 = self.env['memoria.viva.historia'].create({
            'name': 'Lugar Único',
            'description': 'Test 2',
            'website_primario_id': self.website.id,
        })
        self.assertNotEqual(lugar1.slug, lugar2.slug)
        self.assertTrue(lugar2.slug.startswith('lugar-unico-'))
    
    def test_03_aprobar_lugar(self):
        """Test: Aprobar un lugar pendiente (transición de estado)"""
        lugar = self.env['memoria.viva.historia'].create({
            'name': 'Lugar Pendiente',
            'description': 'Test',
            'website_primario_id': self.website.id,
            'state': 'pendiente',
        })
        self.assertEqual(lugar.state, 'pendiente')

        lugar.write({'state': 'aprobado'})
        self.assertEqual(lugar.state, 'aprobado')

    def test_04_rechazar_lugar(self):
        """Test: Rechazar un lugar (transición de estado)"""
        lugar = self.env['memoria.viva.historia'].create({
            'name': 'Lugar Rechazado',
            'description': 'Test',
            'website_primario_id': self.website.id,
            'state': 'pendiente',
        })
        lugar.write({'state': 'rechazado'})
        self.assertEqual(lugar.state, 'rechazado')
    
    def test_05_incrementar_contador_vistas(self):
        """Test: Incrementar contador de vistas"""
        vistas_iniciales = self.lugar.view_count
        self.lugar.incrementar_vistas()
        self.assertEqual(self.lugar.view_count, vistas_iniciales + 1)
    
    def test_06_like_count_computation(self):
        """Test: Computación de contador de likes"""
        # Crear likes
        self.env['memoria.viva.like'].create({
            'lugar_id': self.lugar.id,
            'session_id': 'test-session-1',
        })
        self.env['memoria.viva.like'].create({
            'lugar_id': self.lugar.id,
            'session_id': 'test-session-2',
        })
        
        self.lugar.invalidate_recordset()
        self.assertEqual(self.lugar.like_count, 2)
    
    def test_07_compute_ubicacion(self):
        """Test: Computar campo ubicación"""
        self.assertEqual(self.lugar.ubicacion, '28.123400, -15.567800')
        
        # Lugar sin coordenadas
        lugar_sin_coords = self.env['memoria.viva.historia'].create({
            'name': 'Sin Coordenadas',
            'description': 'Test',
            'website_primario_id': self.website.id,
        })
        self.assertFalse(lugar_sin_coords.ubicacion)
    
    # === Tests de Permisos ===
    
    def test_08_permiso_lectura_publico(self):
        """Test: Lectura pública de lugares aprobados"""
        # Usuario público debería poder leer lugares aprobados
        public_user = self.env.ref('base.public_user')
        lugar_leido = self.env['memoria.viva.historia'].with_user(public_user).search([
            ('id', '=', self.lugar.id)
        ])
        self.assertTrue(lugar_leido)
    
    def test_09_permiso_escritura_admin(self):
        """Test: Solo admin puede modificar"""
        # Usuario demo no debería poder modificar
        with self.assertRaises(AccessError):
            self.lugar.with_user(self.user_demo).write({'name': 'Hackeado'})
    
    # === Tests de Configuración ===
    
    def test_10_configuracion_por_website(self):
        """Test: La configuración vive como campos website-specific."""
        # En setUpClass se escribió memoria_viva_permitir_comentarios=True
        self.assertTrue(self.website.memoria_viva_permitir_comentarios)
        self.assertTrue(self.website.memoria_viva_show_tipo)
        self.assertTrue(self.website.memoria_viva_show_categoria)

        # Y se puede modificar por website.
        self.website.write({'memoria_viva_permitir_comentarios': False})
        self.assertFalse(self.website.memoria_viva_permitir_comentarios)

    def test_11_configuracion_global(self):
        """Test: Aislamiento de la config entre websites."""
        otro = self.env['website'].create({'name': 'Otro Website MV'})
        self.website.write({'memoria_viva_show_coordenadas': True})
        otro.write({'memoria_viva_show_coordenadas': False})
        self.assertTrue(self.website.memoria_viva_show_coordenadas)
        self.assertFalse(otro.memoria_viva_show_coordenadas)
    
    # === Tests de Likes ===
    
    def test_12_crear_like(self):
        """Test: Crear un like para un lugar"""
        like = self.env['memoria.viva.like'].create({
            'lugar_id': self.lugar.id,
            'session_id': 'test-session-abc',
        })
        self.assertTrue(like.id)
        self.assertEqual(like.lugar_id.id, self.lugar.id)
    
    def test_13_like_unico_por_sesion(self):
        """Test: No se puede dar like dos veces con la misma sesión"""
        Like = self.env['memoria.viva.like']
        Like.create({
            'lugar_id': self.lugar.id,
            'session_id': 'session-unica',
        })
        
        # Intentar crear otro like con la misma sesión
        with self.assertRaises(ValidationError):
            Like.create({
                'lugar_id': self.lugar.id,
                'session_id': 'session-unica',
            })
    
    # === Tests de Anuncios ===
    
    def test_14_crear_anuncio(self):
        """Test: Crear un anuncio"""
        anuncio = self.env['memoria.viva.anuncio'].create({
            'name': 'Anuncio Test',
            'tipo': 'banner',
            'titulo': 'Título del Anuncio',
            'subtitulo': 'Subtítulo',
            'descripcion': 'Descripción del anuncio',
            'website_primario_id': self.website.id,
            'state': 'active',
        })
        self.assertTrue(anuncio.id)
        self.assertEqual(anuncio.state, 'active')
    
    def test_15_anuncio_sidebar_disponible(self):
        """Test: Obtener anuncios para sidebar"""
        self.env['memoria.viva.anuncio'].create({
            'name': 'Anuncio Sidebar',
            'tipo': 'sidebar',
            'titulo': 'Oferta Especial',
            'website_primario_id': self.website.id,
            'state': 'active',
            'posicion_sidebar': 'top',
        })
        
        anuncios = self.env['memoria.viva.anuncio'].get_anuncios_sidebar(
            self.website.id, limite=3
        )
        self.assertTrue(len(anuncios) > 0)


@tagged('post_install', '-at_install')
class TestMemoriaVivaImportExport(common.TransactionCase):
    """Tests para importación/exportación"""
    
    @classmethod
    def setUpClass(cls):
        super(TestMemoriaVivaImportExport, cls).setUpClass()
        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
                'domain': 'test.local',
            })
        
        cls.tipo = cls.env['memoria.viva.tipo'].create({
            'name': 'Tipo Import',
        })
    
    def test_01_preparar_datos_importacion(self):
        """Test: Preparar datos para importación"""
        Historia = self.env['memoria.viva.historia']
        
        valores = {
            'name': 'Lugar Import Test',
            'description': 'Descripción importada',
            'tipo_id': self.tipo.id,
            'direccion': 'Dirección test',
            'website_primario_id': self.website.id,
        }
        
        datos_preparados = Historia._prepare_import_values(valores)
        self.assertEqual(datos_preparados['name'], 'Lugar Import Test')
        self.assertEqual(datos_preparados['state'], 'aprobado')
    
    def test_02_exportar_datos(self):
        """Test: Exportar datos de lugares"""
        lugar = self.env['memoria.viva.historia'].create({
            'name': 'Lugar Export',
            'description': 'Para exportar',
            'website_primario_id': self.website.id,
            'direccion': 'Calle Export 123',
            'publicador_nombre': 'Exportador',
            'publicador_telefono': '999888777',
            'publicador_email': 'export@test.com',
            'state': 'aprobado',
        })
        
        datos = lugar._export_data()
        self.assertIn('name', datos)
        self.assertIn('description', datos)
        self.assertEqual(datos['name'], 'Lugar Export')
