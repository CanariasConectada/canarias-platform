# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command
from odoo.tests import HttpCase, tagged
from odoo.tests.common import new_test_user


@tagged("post_install", "-at_install")
class TestCompanySwitcherLabels(HttpCase):
    """The switcher is the list the operators scan to pick one of 282 shops.

    ``web`` builds it from ``comp.name`` instead of ``display_name``, so it
    was the one place the trade name never reached.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Company = cls.env["res.company"]
        cls.savage = Company.create(
            {"name": "RCZ Mario Alvarez Borges", "comercial": "RCZ 24 Horas Savage"}
        )
        cls.plain = Company.create({"name": "RCZ Sin Rotulo SL"})
        cls.user = new_test_user(
            cls.env,
            login="rcz_switcher",
            password="rcz_switcher_pw",
            groups="base.group_user,base.group_multi_company",
            company_id=cls.savage.id,
            company_ids=[Command.set([cls.savage.id, cls.plain.id])],
        )

    def _allowed_companies(self):
        self.env.flush_all()
        # _get_company_ids is an ormcache, and the companies were linked to
        # the user after the registry was built for this test.
        self.env.registry.clear_cache()
        self.authenticate("rcz_switcher", "rcz_switcher_pw")
        info = self.make_jsonrpc_request("/web/session/get_session_info")
        # JSON object keys are strings, the payload is keyed by company id.
        return info["user_companies"]["allowed_companies"]

    def test_the_switcher_shows_the_trade_name(self):
        allowed = self._allowed_companies()
        self.assertEqual(
            allowed[str(self.savage.id)]["name"],
            "RCZ 24 Horas Savage (RCZ Mario Alvarez Borges)",
        )

    def test_the_switcher_keeps_the_legal_name_without_a_trade_name(self):
        allowed = self._allowed_companies()
        self.assertEqual(allowed[str(self.plain.id)]["name"], "RCZ Sin Rotulo SL")
