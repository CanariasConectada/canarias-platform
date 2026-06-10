# -*- coding: utf-8 -*-
"""
Tests para el sistema de comentarios de Lugares de Interés
"""
from odoo.tests import common, tagged
from odoo.exceptions import ValidationError

DUMMY_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAH"
    "ggJ/PchI7wAAAABJRU5ErkJggg=="
)


@tagged('post_install', '-at_install')
class TestLugaresInteresComentarios(common.TransactionCase):
    """Tests para comentarios y moderación"""

    @classmethod
    def setUpClass(cls):
        super(TestLugaresInteresComentarios, cls).setUpClass()

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

        tipo = cls.env['lugares.interes.tipo'].create({'name': 'Tipo Test'})
        categoria = cls.env['lugares.interes.categoria'].create({
            'name': 'Test',
            'tipo_id': tipo.id,
        })
        cls.lugar = cls.env['lugares.interes.historia'].create({
            'name': 'Lugar con Comentarios',
            'description': 'Test de comentarios',
            'website_primario_id': cls.website.id,
            'categoria_id': categoria.id,
            'state': 'aprobado',
            'image_main': DUMMY_IMAGE,
        })

        cls.Comentario = cls.env['lugares.interes.comentario']
        cls.PalabraProhibida = cls.env['lugares.interes.palabra.prohibida']

    def test_01_crear_comentario_simple(self):
        """Test: Crear un comentario básico"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Este es un comentario de prueba',
            'autor_id': self.user_demo.id,
        })
        self.assertTrue(comentario.id)
        self.assertEqual(comentario.lugar_id.id, self.lugar.id)
        self.assertEqual(comentario.contenido, 'Este es un comentario de prueba')
        self.assertEqual(comentario.autor_id.id, self.user_demo.id)

    def test_02_comentario_aprobado_por_defecto(self):
        """Test: Comentario se aprueba si no tiene palabras prohibidas"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario limpio y apropiado',
            'autor_id': self.user_demo.id,
        })
        self.assertEqual(comentario.estado, 'aprobado')
        self.assertFalse(comentario.contiene_palabras_prohibidas)

    def test_03_comentario_pendiente_con_palabra_prohibida(self):
        """Test: Comentario con palabra prohibida queda pendiente"""
        self.PalabraProhibida.create({'name': 'spam'})
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Este es un mensaje spam',
            'autor_id': self.user_demo.id,
        })
        self.assertEqual(comentario.estado, 'pendiente')
        self.assertTrue(comentario.contiene_palabras_prohibidas)

    def test_04_aprobar_comentario(self):
        """Test: Aprobar un comentario pendiente"""
        self.PalabraProhibida.create({'name': 'moderar'})
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario para moderar',
            'autor_id': self.user_demo.id,
        })
        self.assertEqual(comentario.estado, 'pendiente')
        comentario.action_aprobar()
        self.assertEqual(comentario.estado, 'aprobado')

    def test_05_rechazar_comentario(self):
        """Test: Rechazar un comentario"""
        comentario = self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Comentario para rechazar',
            'autor_id': self.user_demo.id,
        })
        comentario.action_rechazar()
        self.assertEqual(comentario.estado, 'rechazado')

    def test_06_get_comentarios_aprobados(self):
        """Test: Obtener comentarios aprobados de un lugar"""
        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Aprobado 1',
            'autor_id': self.user_demo.id,
            'estado': 'aprobado',
        })
        self.Comentario.sudo().create({
            'lugar_id': self.lugar.id,
            'contenido': 'Aprobado 2',
            'autor_id': self.user_demo.id,
            'estado': 'aprobado',
        })
        comentarios = self.Comentario.get_comentarios_aprobados(self.lugar.id)
        self.assertTrue(len(comentarios) >= 2)
