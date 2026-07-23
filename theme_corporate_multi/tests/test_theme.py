# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestThemeCorporateMulti(HttpCase):
    """Smoke-check the themed website home page."""

    def test_homepage_renders_without_odoo_branding(self):
        response = self.url_open("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "odoo_logo_tiny.png",
            response.text,
            "The 'Powered by Odoo' branding must not be rendered",
        )
