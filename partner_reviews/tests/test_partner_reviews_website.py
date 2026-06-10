# -*- coding: utf-8 -*-
from odoo.tests.common import TransactionCase


class TestPartnerReviewWebsite(TransactionCase):

    def setUp(self):
        super(TestPartnerReviewWebsite, self).setUp()
        self.partner = self.env['res.partner'].create({
            'name': 'Comercio Web Test',
            'enable_reviews': True,
        })
        self.user = self.env['res.users'].create({
            'name': 'Web Test User',
            'login': 'web_test_user',
            'password': 'test123',
        })
        self.env['partner.review.settings'].create({
            'permitir_comentarios': True,
        })

    def test_settings_singleton(self):
        settings = self.env['partner.review.settings'].get_settings()
        self.assertTrue(settings)
        self.assertTrue(settings.permitir_comentarios)
