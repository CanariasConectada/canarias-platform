# -*- coding: utf-8 -*-
from odoo.tests import HttpCase, tagged

CC_LOGO = "/website_login_branding/static/src/img/canarias_conectada_logo.webp"
ZCA_LOGO = "/website_login_branding/static/src/img/zca_logo.png"


@tagged("post_install", "-at_install")
class TestLoginBranding(HttpCase):
    """Check that both brand logos are rendered on the website auth pages."""

    def _assert_branding(self, body):
        self.assertIn(CC_LOGO, body, "Canarias Conectada logo missing")
        self.assertIn(ZCA_LOGO, body, "ZCA logo missing")

    def test_login_page_has_logos(self):
        response = self.url_open("/web/login")
        self.assertEqual(response.status_code, 200)
        self._assert_branding(response.text)

    def test_signup_page_has_logos(self):
        # Public signup can be disabled per database, in which case the
        # route answers 404 and there is no page to check.
        response = self.url_open("/web/signup")
        self.assertIn(response.status_code, (200, 404))
        if response.status_code == 200:
            self.assertIn("oe_website_login_container", response.text)
            self._assert_branding(response.text)

    def test_reset_password_page_has_logos(self):
        response = self.url_open("/web/reset_password")
        self.assertEqual(response.status_code, 200)
        self.assertIn("oe_website_login_container", response.text)
        self._assert_branding(response.text)
