# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

PNG = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc00000030101007f6a6b8d0000000049454e44ae426082"
))


@tagged("post_install", "-at_install")
class TestMicrositeHero(TransactionCase):
    """The hero's size lives in the stylesheet, its picture inline."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create(
            {"name": "Hero Shop", "microsite_hero_image": PNG}
        )
        cls.website = cls.env["website"].create(
            {"name": "Hero Shop site", "company_id": cls.company.id}
        )
        cls.company.website_id = cls.website

    def _render(self):
        return self.env["ir.qweb"]._render(
            "partner_microsite_manager.microsite_homepage_content",
            {"website": self.website},
        )

    def test_the_picture_is_inline_and_the_size_is_not(self):
        html = self._render()
        self.assertIn("o_pmm_hero", html)
        self.assertIn("/web/image/res.company/%s/microsite_hero_image" % self.company.id, html)
        self.assertNotIn("60vh", html, "size belongs to the stylesheet, where a phone differs")
        self.assertNotIn("pt96", html)

    def test_no_picture_keeps_the_gradient(self):
        self.company.microsite_hero_image = False
        html = self._render()
        self.assertIn("linear-gradient", html)
        self.assertIn("o_pmm_hero", html)
