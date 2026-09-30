# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestShopFrontend(HttpCase):
    """Smoke-check the tweaked shop page."""

    def test_shop_page_renders(self):
        # The old shop-directory-header was replaced by the curated hero of
        # website_sale_canarias on 2026-08-26; asserting it kept this test
        # red against reality. The toolbar is still this module's markup.
        response = self.url_open("/shop")
        self.assertEqual(response.status_code, 200)
        self.assertIn("shop-directory-toolbar", response.text)
