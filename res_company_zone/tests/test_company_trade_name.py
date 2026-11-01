# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from lxml import etree

from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged("post_install", "-at_install")
class TestCompanyTradeName(TransactionCase):
    """Companies answer to their trade name.

    Client feedback: "when we search a shop by its name we never find it" --
    the name they type is the one on the sign, while ``res.company.name`` is
    the owner's own name or the registered "S.L." for 125 of 282 shops.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Company = cls.env["res.company"]
        cls.savage = cls.Company.create(
            {"name": "RCZ Mario Alvarez Borges", "comercial": "RCZ 24 Horas Savage"}
        )
        cls.plain = cls.Company.create({"name": "RCZ Sin Rotulo SL"})

    def test_the_trade_name_lands_on_the_partner(self):
        """The field is the partner's own (l10n_es_partner), opened from the
        company form in both directions: no second copy to keep in sync."""
        self.assertEqual(self.savage.partner_id.comercial, "RCZ 24 Horas Savage")
        self.savage.comercial = "RCZ Savage Renamed"
        self.assertEqual(self.savage.partner_id.comercial, "RCZ Savage Renamed")

    def test_name_search_finds_the_company_by_its_trade_name(self):
        """The point of the change: every company many2one goes through
        name_search, and it only matched the legal name."""
        found = [cid for cid, _label in self.Company.name_search("Horas Savage")]
        self.assertIn(self.savage.id, found)
        self.assertNotIn(self.plain.id, found)

    def test_name_search_still_finds_the_legal_name(self):
        found = [cid for cid, _label in self.Company.name_search("Sin Rotulo")]
        self.assertIn(self.plain.id, found)

    def test_display_name_search_matches_the_trade_name(self):
        """The web client's quick search on relational fields hits
        ``display_name`` directly, not ``name_search``."""
        found = self.Company.search([("display_name", "ilike", "Horas Savage")])
        self.assertIn(self.savage, found)

    def test_display_name_shows_the_trade_name_then_the_legal_one(self):
        self.assertEqual(
            self.savage.display_name,
            "RCZ 24 Horas Savage (RCZ Mario Alvarez Borges)",
        )

    def test_display_name_without_a_trade_name_is_the_plain_name(self):
        self.assertEqual(self.plain.display_name, "RCZ Sin Rotulo SL")

    def test_display_name_does_not_repeat_an_identical_trade_name(self):
        """Half the migrated trade names are the legal name typed again, in
        another case; "ABINFORMATICA (Abinformatica)" would be noise."""
        self.plain.comercial = "rcz sin rotulo sl"
        self.assertEqual(self.plain.display_name, "RCZ Sin Rotulo SL")

    def test_display_name_follows_a_trade_name_change(self):
        self.plain.comercial = "RCZ Rotulo Nuevo"
        self.assertEqual(
            self.plain.display_name, "RCZ Rotulo Nuevo (RCZ Sin Rotulo SL)"
        )
        self.plain.comercial = False
        self.assertEqual(self.plain.display_name, "RCZ Sin Rotulo SL")

    def _search_field_domain(self, field_name, value):
        """Evaluate the ``filter_domain`` of a <field> of the combined
        search view, inheritance applied, the way the search box does."""
        view = self.env.ref("res_company_search_view.view_res_company_search")
        arch = etree.fromstring(
            self.Company.get_view(view_id=view.id, view_type="search")["arch"]
        )
        nodes = arch.xpath(f"//field[@name='{field_name}']")
        self.assertTrue(nodes, f"no <field name='{field_name}'> in the search view")
        filter_domain = nodes[0].get("filter_domain")
        if not filter_domain:
            return [(field_name, "ilike", value)]
        return safe_eval(filter_domain, {"self": value})

    def test_the_search_box_matches_the_trade_name(self):
        """Typing in the Companies search box searches ``name``; its domain
        now covers the trade name too, without losing the OCA VAT match."""
        found = self.Company.search(self._search_field_domain("name", "Horas Savage"))
        self.assertIn(self.savage, found)
        self.assertNotIn(self.plain, found)
        found = self.Company.search(self._search_field_domain("name", "Sin Rotulo"))
        self.assertIn(self.plain, found)

    def test_the_search_view_offers_the_trade_name_on_its_own(self):
        found = self.Company.search(self._search_field_domain("comercial", "Savage"))
        self.assertIn(self.savage, found)
        self.assertNotIn(self.plain, found)
