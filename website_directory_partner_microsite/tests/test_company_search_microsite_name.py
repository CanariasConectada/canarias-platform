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

    The search box domain is restated in full by this module, so every leaf
    is exercised here: a leaf that silently drops out of the restatement
    would otherwise go unnoticed.
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
        cls.Company = cls.env["res.company"]
        cls.shop = cls.Company.create(
            {
                "name": "Dayra Search Test SL",
                "comercial": "Rotulo Search Test",
                "microsite_name": "La Belle Search Test",
                "vat": "ESB12345674",
                "company_registry": "RM-SEARCH-TEST-0042",
            }
        )
        cls.plain = cls.Company.create({"name": "Plain Search Test SL"})

    def _typed_in_the_search_box(self, term):
        """What the web client searches when `term` is typed in the box."""
        arch = self.Company.get_view(view_type="search")["arch"]
        node = etree.fromstring(arch).xpath("//field[@name='name']")[0]
        return self.Company.search(safe_eval(node.get("filter_domain"), {"self": term}))

    def test_typing_the_microsite_name_finds_the_company(self):
        found = self._typed_in_the_search_box("belle search")
        self.assertIn(self.shop, found)
        self.assertNotIn(self.plain, found)

    def test_typing_the_legal_name_still_finds_the_company(self):
        self.assertIn(self.shop, self._typed_in_the_search_box("dayra search"))

    def test_typing_the_trade_name_still_finds_the_company(self):
        self.assertIn(self.shop, self._typed_in_the_search_box("rotulo search"))

    def test_typing_the_vat_still_finds_the_company(self):
        self.assertIn(self.shop, self._typed_in_the_search_box("B12345674"))

    def test_typing_the_registry_number_still_finds_the_company(self):
        self.assertIn(self.shop, self._typed_in_the_search_box("RM-SEARCH-TEST-0042"))

    def test_a_term_matching_nothing_finds_nothing(self):
        self.assertFalse(self._typed_in_the_search_box("zzz-no-company-matches-xq9"))

    def test_an_empty_microsite_name_does_not_match_an_unrelated_term(self):
        self.assertFalse(self.plain.microsite_name)
        found = self._typed_in_the_search_box("La Belle Search Test")
        self.assertNotIn(self.plain, found)
