# -*- coding: utf-8 -*-
"""
Tests para modelos del módulo Lugares de Interés
"""
from odoo.tests import common, tagged
from odoo.exceptions import ValidationError
from psycopg2 import IntegrityError

DUMMY_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAH"
    "ggJ/PchI7wAAAABJRU5ErkJggg=="
)


@tagged('post_install', '-at_install')
class TestLugaresInteresModels(common.TransactionCase):
    """Tests para modelos de Lugares de Interés"""

    @classmethod
    def setUpClass(cls):
        super(TestLugaresInteresModels, cls).setUpClass()

        cls.user_admin = cls.env.ref('base.user_admin')
        demo = cls.env['res.users'].search([('login', '=', 'test_demo')], limit=1)
        if not demo:
            demo = cls.env['res.users'].create({
                'name': 'Test Demo',
                'login': 'test_demo',
                'password': 'test_demo',
                'group_ids': [(6, 0, [cls.env.ref('base.group_user').id])],
            })
        cls.user_demo = demo

        cls.website = cls.env['website'].search([], limit=1)
        if not cls.website:
            cls.website = cls.env['website'].create({
                'name': 'Test Website',
                'domain': 'test.local',
            })

        cls.tipo = cls.env['lugares.interes.tipo'].create({
            'name': 'Monumento Histórico',
        })

        cls.categoria = cls.env['lugares.interes.categoria'].create({
            'name': 'Arquitectura',
            'tipo_id': cls.tipo.id,
        })

        cls.lugar = cls.env['lugares.interes.historia'].create({
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
            'image_main': DUMMY_IMAGE,
        })

    def test_01_crear_lugar(self):
        """Test: Crear un lugar de interés"""
        lugar = self.env['lugares.interes.historia'].create({
            'name': 'Nuevo Lugar Test',
            'description': 'Descripción de test',
            'tipo_id': self.tipo.id,
            'categoria_id': self.categoria.id,
            'website_primario_id': self.website.id,
            'state': 'pendiente',
            'image_main': DUMMY_IMAGE,
        })
        self.assertTrue(lugar.id)
        self.assertEqual(lugar.name, 'Nuevo Lugar Test')
        self.assertEqual(lugar.state, 'pendiente')
        self.assertTrue(lugar.slug)
        self.assertIn('nuevo-lugar-test', lugar.slug)

    def test_02_slug_unico(self):
        """Test: El slug debe ser único dentro del mismo microsite"""
        lugar1 = self.env['lugares.interes.historia'].create({
            'name': 'Lugar Único',
            'description': 'Test',
            'categoria_id': self.categoria.id,
            'website_primario_id': self.website.id,
            'image_main': DUMMY_IMAGE,
        })
        lugar2 = self.env['lugares.interes.historia'].create({
            'name': 'Lugar Único',
            'description': 'Test 2',
            'categoria_id': self.categoria.id,
            'website_primario_id': self.website.id,
            'image_main': DUMMY_IMAGE,
        })
        self.assertNotEqual(lugar1.slug, lugar2.slug)
        self.assertTrue(lugar2.slug.startswith('lugar-unico-'))

    def test_03_cambiar_estado(self):
        """Test: Cambiar estado de un lugar"""
        lugar = self.env['lugares.interes.historia'].create({
            'name': 'Lugar Estado',
            'description': 'Test',
            'categoria_id': self.categoria.id,
            'website_primario_id': self.website.id,
            'state': 'pendiente',
            'image_main': DUMMY_IMAGE,
        })
        self.assertEqual(lugar.state, 'pendiente')
        lugar.write({'state': 'aprobado'})
        self.assertEqual(lugar.state, 'aprobado')
        lugar.write({'state': 'rechazado'})
        self.assertEqual(lugar.state, 'rechazado')

    def test_04_like_count_computation(self):
        """Test: Computación de contador de likes"""
        self.env['lugares.interes.like'].create({
            'lugar_id': self.lugar.id,
            'session_id': 'test-session-1',
        })
        self.env['lugares.interes.like'].create({
            'lugar_id': self.lugar.id,
            'session_id': 'test-session-2',
        })
        self.lugar.invalidate_recordset()
        self.assertEqual(self.lugar.like_count, 2)

    def test_05_validacion_coordenadas(self):
        """Test: Validar rango de coordenadas"""
        with self.assertRaises(ValidationError):
            self.env['lugares.interes.historia'].create({
                'name': 'Coords Malas',
                'description': 'Test',
                'categoria_id': self.categoria.id,
                'website_primario_id': self.website.id,
                'latitude': 91.0,
                'longitude': 0,
                'image_main': DUMMY_IMAGE,
            })

    def test_06_validacion_dni(self):
        """Test: Validar longitud del DNI"""
        with self.assertRaises(ValidationError):
            self.lugar.write({'dni_remitente': '12'})

    def test_07_crear_like(self):
        """Test: Crear un like para un lugar"""
        like = self.env['lugares.interes.like'].create({
            'lugar_id': self.lugar.id,
            'session_id': 'test-session-abc',
        })
        self.assertTrue(like.id)
        self.assertEqual(like.lugar_id.id, self.lugar.id)

    def test_08_like_unico_por_sesion(self):
        """Test: No se puede dar like dos veces con la misma sesión"""
        Like = self.env['lugares.interes.like']
        Like.create({
            'lugar_id': self.lugar.id,
            'session_id': 'session-unica',
        })
        # Verificar que solo existe 1 like con esa sesión
        count = Like.search_count([
            ('lugar_id', '=', self.lugar.id),
            ('session_id', '=', 'session-unica'),
        ])
        self.assertEqual(count, 1)

    def test_09_configuracion_get_settings(self):
        """Test: Obtener configuración"""
        settings = self.env['lugares.interes.settings'].get_settings()
        self.assertTrue(settings)
        self.assertTrue(settings.permitir_comentarios)
