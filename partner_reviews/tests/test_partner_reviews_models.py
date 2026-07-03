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

    def test_rating_notifica_partner(self):
        """La notificación por email al comercio no debe reventar (regresión:
        NameError por llamar a escapeHtml en lugar de html_escape)."""
        self.partner.email = 'comercio@test.example'
        rating = self.env['partner.review.rating'].create({
            'partner_id': self.partner.id,
            'user_id': self.user.id,
            'rating': 4,
        })
        mails_before = self.env['mail.mail'].sudo().search_count([])
        rating._notificar_partner()
        mails_after = self.env['mail.mail'].sudo().search_count([])
        self.assertGreaterEqual(mails_after, mails_before)

    def test_comment_moderation_notifica_moderadores(self):
        """Un comentario con palabras prohibidas debe crear una actividad para
        cada moderador (regresión: el search sobre el campo inexistente
        groups_id fallaba en silencio y nadie recibía nada)."""
        moderator_group = self.env.ref('partner_reviews.group_partner_reviews_moderator')
        moderator = self.env['res.users'].create({
            'name': 'Moderador Test',
            'login': 'test_moderator_reviews',
            'group_ids': [(4, moderator_group.id)],
        })
        self.env['partner.review.palabra.prohibida'].create({'name': 'vetada'})
        comment = self.env['partner.review.comment'].create({
            'partner_id': self.partner.id,
            'autor_id': self.user.id,
            'contenido': 'Esta palabra está vetada seguro',
        })
        self.assertEqual(comment.estado, 'pendiente')
        activity = self.env['mail.activity'].search([
            ('res_model_id', '=', self.env['ir.model']._get_id('partner.review.comment')),
            ('res_id', '=', comment.id),
            ('user_id', '=', moderator.id),
        ])
        self.assertTrue(activity, 'El moderador debe recibir una actividad de moderación')

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
