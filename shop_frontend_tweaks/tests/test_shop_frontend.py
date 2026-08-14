# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestShopFrontend(HttpCase):
    """Smoke-check the tweaked shop page."""

    def test_shop_page_renders(self):
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("shop-directory-toolbar", response.text)
        self.assertIn("shop-directory-header", response.text)
