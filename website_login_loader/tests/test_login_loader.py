# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""The loader reaches the served auth page, and reaches it inline.

There is no behaviour to assert server side: the module is one template. What
CAN silently break is delivery -- an xpath that stops matching after another
module rewrites the login card, or somebody moving the styles into a bundle,
which would defeat the entire point of the module.
"""
from odoo.tests import tagged
from odoo.tests.common import HttpCase


@tagged("post_install", "-at_install")
class TestLoginLoader(HttpCase):
    def setUp(self):
        super().setUp()
        self.page = self.url_open("/web/login").text

    def test_loader_markup_is_served_on_the_login_page(self):
        """The xpath still matches whatever the card looks like today."""
        self.assertIn('id="o_cc_ldr"', self.page)
        self.assertIn("o_cc_ldr_bar", self.page)

    def test_curtain_starts_hidden(self):
        """The no-JavaScript guarantee, asserted on the served bytes.

        If this ever renders without `hidden`, a visitor whose browser does not
        run the script gets a permanent cover over the login form.
        """
        self.assertRegex(self.page, r'id="o_cc_ldr"[^>]*hidden')

    def test_styles_and_script_are_inline(self):
        """Not in a bundle, which is the module's whole reason to exist.

        A `<link>` or `<script src>` would arrive inside the render-blocking
        payload whose wait this reports on, so it could only appear once the
        waiting was over.
        """
        self.assertIn(".o_cc_ldr_bar", self.page, "styles inlined in the page")
        self.assertIn("o_cc_loading", self.page, "script inlined in the page")

    def test_live_region_is_present_from_the_start(self):
        """Announcements need a region already in the accessibility tree.

        Revealing a node that was `hidden` is not reliably announced; changing
        the text of a region that was always there is.
        """
        self.assertIn("o_cc_ldr_sr", self.page)
        self.assertIn('aria-live="polite"', self.page)
