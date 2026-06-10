# -*- coding: utf-8 -*-
"""
Tests para controladores web de Lugares de Interés
"""
from odoo.tests import common, tagged

DUMMY_IMAGE = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAH"
    "ggJ/PchI7wAAAABJRU5ErkJggg=="
)


@tagged('post_install', '-at_install')
class TestLugaresInteresWebsite(common.TransactionCase):
    """Tests para endpoints web (lógica de controladores)"""

    @classmethod
    def setUpClass(cls):
        super(TestLugaresInteresWebsite, cls).setUpClass()

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

        cls.config = cls.env['lugares.interes.settings'].create({
            'permitir_comentarios': True,
        })

        cls.tipo = cls.env['lugares.interes.tipo'].create({
            'name': 'Tipo Test Web',
        })
        cls.categoria = cls.env['lugares.interes.categoria'].create({
            'name': 'Categoria Test Web',
            'tipo_id': cls.tipo.id,
        })

        cls.lugar = cls.env['lugares.interes.historia'].create({
            'name': 'Lugar Web Test',
            'description': 'Descripción web',
            'tipo_id': cls.tipo.id,
            'categoria_id': cls.categoria.id,
            'website_primario_id': cls.website.id,
            'state': 'aprobado',
            'slug': 'lugar-web-test',
            'image_main': DUMMY_IMAGE,
        })

    def test_01_lugar_aprobado_visible(self):
        """Test: Lugar aprobado tiene estado correcto"""
        self.assertEqual(self.lugar.state, 'aprobado')
        self.assertTrue(self.lugar.slug)

    def test_02_filtro_por_barrio(self):
        """Test: Filtrar lugares por barrio"""
        self.lugar.write({'barrio': 'Guanarteme'})
        lugares = self.env['lugares.interes.historia'].search([
            ('state', '=', 'aprobado'),
            ('barrio', 'ilike', 'Guanarteme'),
        ])
        self.assertTrue(self.lugar.id in lugares.ids)

    def test_03_ordenar_por_valoracion(self):
        """Test: Ordenar lugares por valoración"""
        lugares = self.env['lugares.interes.historia'].search([
            ('state', '=', 'aprobado'),
        ], order='rating_avg desc')
        self.assertTrue(len(lugares) >= 1)

    def test_04_generacion_slug(self):
        """Test: Slug se genera automáticamente"""
        lugar = self.env['lugares.interes.historia'].create({
            'name': 'Nuevo Lugar Slug',
            'description': 'Test',
            'categoria_id': self.categoria.id,
            'website_primario_id': self.website.id,
            'image_main': DUMMY_IMAGE,
        })
        self.assertTrue(lugar.slug)
        self.assertIn('nuevo-lugar-slug', lugar.slug)
