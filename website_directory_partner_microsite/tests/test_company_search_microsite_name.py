# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from lxml import etree

from odoo.tests import tagged
from odoo.tests.common import TransactionCase
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install")
class TestCompanySearchMicrositeName(TransactionCase):
    """Settings > Companies finds a shop by the heading of its microsite.

    The operators know the shops by what the site shows, which is
    `microsite_name` when it is set, while the search box only matched the
    legal name, the trade name, the VAT and the registry number.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Creating a company on a copy of production trips
        # website_sale_collect's warehouse/company constraint; only patched
        # when that module is there, so a clean CI database is left alone.
        carrier_cls = type(cls.env["delivery.carrier"])
        if hasattr(carrier_cls, "_check_warehouses_have_same_company"):
            cls.startClassPatcher(
                patch.object(
                    carrier_cls,
                    "_check_warehouses_have_same_company",
                    lambda self: None,
                )
            )
        cls.shop = cls.env["res.company"].create(
            {"name": "Dayra Search Test SL", "microsite_name": "La Belle Search Test"}
        )

    def _search_box_domain(self):
        arch = self.env["res.company"].get_view(view_type="search")["arch"]
        node = etree.fromstring(arch).xpath("//field[@name='name']")[0]
        return node.get("filter_domain")

    def test_the_search_box_domain_reaches_the_microsite_name(self):
        self.assertIn("('microsite_name', 'ilike', self)", self._search_box_domain())

    def test_typing_the_microsite_name_finds_the_company(self):
        domain = safe_eval(self._search_box_domain(), {"self": "belle search"})
        found = self.env["res.company"].search(domain)
        self.assertIn(self.shop, found)

    def test_the_legal_name_still_finds_the_company(self):
        domain = safe_eval(self._search_box_domain(), {"self": "dayra search"})
        self.assertIn(self.shop, self.env["res.company"].search(domain))
