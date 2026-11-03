# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import base64

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

# A 1x1 PNG, twice with a different pixel so the two logos differ.
PNG_A = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360f8cfc00000030101007f6a6b8d0000000049454e44ae426082"
))
PNG_B = base64.b64encode(bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c636078c1f01f0003040101c9c7e1560000000049454e44ae426082"
))


@tagged("post_install", "-at_install")
class TestLogoFollowsCompany(TransactionCase):
    """The header shows the logo the merchant just changed."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.shop = cls.env["res.company"].create({"name": "Logo Shop", "logo": PNG_A})
        cls.site = cls.env["website"].create(
            {"name": "Logo Shop site", "company_id": cls.shop.id, "logo": PNG_A}
        )
        cls.shop.website_id = cls.site

    def test_changing_the_company_logo_changes_the_header(self):
        self.shop.write({"logo": PNG_B})
        self.assertEqual(self.site.logo, PNG_B)

    def test_a_write_without_the_logo_leaves_the_header_alone(self):
        self.site.write({"logo": PNG_B})
        self.shop.write({"name": "Logo Shop, renamed"})
        self.assertEqual(self.site.logo, PNG_B)

    def test_another_shops_header_is_untouched(self):
        other = self.env["res.company"].create({"name": "Other Shop", "logo": PNG_A})
        other_site = self.env["website"].create(
            {"name": "Other site", "company_id": other.id, "logo": PNG_A}
        )
        self.shop.write({"logo": PNG_B})
        self.assertEqual(other_site.logo, PNG_A)
