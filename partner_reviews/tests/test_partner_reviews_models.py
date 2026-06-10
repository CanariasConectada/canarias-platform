# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase
from odoo.exceptions import ValidationError


class TestPartnerReviewModels(TransactionCase):

    def setUp(self):
        super(TestPartnerReviewModels, self).setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Comercio Test',
            'enable_reviews': True,
        })
        self.user = self.env['res.users'].create({
            'name': 'Test User',
            'login': 'test_user_reviews',
        })

    def test_create_rating(self):
        rating = self.env['partner.review.rating'].create({
            'partner_id': self.partner.id,
            'user_id': self.user.id,
            'rating': 5,
        })
        self.assertEqual(rating.rating, 5)
        self.assertEqual(self.partner.review_rating_avg, 5.0)
        self.assertEqual(self.partner.review_rating_count, 1)

    def test_rating_unique_constraint(self):
        self.env['partner.review.rating'].create({
            'partner_id': self.partner.id,
            'user_id': self.user.id,
            'rating': 4,
        })
        self.env.cr.flush()
        from psycopg2.errors import UniqueViolation
        with self.assertRaises(UniqueViolation):
            self.env['partner.review.rating'].create({
                'partner_id': self.partner.id,
                'user_id': self.user.id,
                'rating': 3,
            })

    def test_rating_range_validation(self):
        with self.assertRaises(ValidationError):
            self.env['partner.review.rating'].create({
                'partner_id': self.partner.id,
                'user_id': self.user.id,
                'rating': 6,
            })

    def test_comment_creation(self):
        comment = self.env['partner.review.comment'].create({
            'partner_id': self.partner.id,
            'autor_id': self.user.id,
            'contenido': 'Excelente servicio',
        })
        self.assertEqual(comment.estado, 'aprobado')
        self.assertFalse(comment.contiene_palabras_prohibidas)

    def test_comment_moderation(self):
        self.env['partner.review.palabra.prohibida'].create({'name': 'prohibida'})
        comment = self.env['partner.review.comment'].create({
            'partner_id': self.partner.id,
            'autor_id': self.user.id,
            'contenido': 'Esta palabra está prohibida',
        })
        self.assertEqual(comment.estado, 'pendiente')
        self.assertTrue(comment.contiene_palabras_prohibidas)

    def test_comment_response_level(self):
        comment1 = self.env['partner.review.comment'].create({
            'partner_id': self.partner.id,
            'autor_id': self.user.id,
            'contenido': 'Comentario principal',
        })
        comment2 = self.env['partner.review.comment'].create({
            'partner_id': self.partner.id,
            'autor_id': self.user.id,
            'contenido': 'Respuesta',
            'parent_id': comment1.id,
        })
        self.assertTrue(comment2.es_respuesta)
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            self.env['partner.review.comment'].create({
                'partner_id': self.partner.id,
                'autor_id': self.user.id,
                'contenido': 'Segundo nivel',
                'parent_id': comment2.id,
            })
