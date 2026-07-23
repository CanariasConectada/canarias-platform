# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged


@tagged("post_install", "-at_install")
class TestThemeCorporateMulti(HttpCase):
    """Smoke-check the themed website home page.

    Theme views only take effect on websites where the theme is applied,
    so the test applies it to the current website first — installing the
    module alone changes nothing.
    """

    def setUp(self):
        super().setUp()
        self.theme = self.env["ir.module.module"].search(
            [("name", "=", "theme_corporate_multi")], limit=1
        )
        self.website = self.env["website"].get_current_website()
        if self.website.theme_id != self.theme:
            self.website.theme_id = self.theme
            self.theme.with_context(apply_new_theme=True)._theme_load(self.website)

    def test_homepage_renders_without_odoo_branding(self):
        response = self.url_open("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(
            "odoo_logo_tiny.png",
            response.text,
            "The 'Powered by Odoo' branding must not be rendered",
        )
