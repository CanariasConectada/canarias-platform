# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestZoneCompanyOwnership(TransactionCase):
    """A merchant's catalogue and staff follow the merchant's neighbourhood.

    Asked for on 2026-08-14: "la empresa que se va a agregar también es de la
    zona comercial a la que la empresa pertenece, si a la empresa le cambiamos
    la zona comercial, pues los productos y usuarios también deben
    actualizarse".
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zone_guanarteme = cls.env["res.company"].create(
            {"name": "Zone Guanarteme", "zone_company_key": "guanarteme"}
        )
        cls.zone_tamaraceite = cls.env["res.company"].create(
            {"name": "Zone Tamaraceite", "zone_company_key": "tamaraceite"}
        )
        cls.platform = cls.env.ref("base.main_company")
        cls.shop = cls.env["res.company"].create(
            {"name": "Zone Test Shop", "commercial_zone": "guanarteme"}
        )

    def _product(self, owners):
        return self.env["product.template"].create(
            {"name": "Zone Test Product", "company_ids": [(6, 0, owners.ids)]}
        )

    def test_a_new_product_joins_its_zone(self):
        product = self._product(self.shop | self.platform)
        self.assertIn(self.zone_guanarteme, product.company_ids)
        self.assertIn(self.shop, product.company_ids)
        self.assertIn(self.platform, product.company_ids)

    def test_moving_the_shop_moves_its_catalogue(self):
        """The whole request, in one assertion."""
        product = self._product(self.shop | self.platform)

        self.shop.commercial_zone = "tamaraceite"

        product.invalidate_recordset(["company_ids"])
        self.assertIn(self.zone_tamaraceite, product.company_ids)
        self.assertNotIn(
            self.zone_guanarteme,
            product.company_ids,
            "a shop that moved must stop appearing in the zone it left",
        )

    def test_moving_to_no_zone_leaves_only_the_platform(self):
        """"si no está en ninguna, pues sólo estará con canarias conectada"."""
        product = self._product(self.shop | self.platform)

        self.shop.commercial_zone = "canarias"

        product.invalidate_recordset(["company_ids"])
        self.assertEqual(product.company_ids, self.shop | self.platform)

    def test_a_zone_shared_with_another_owner_survives(self):
        """One owner leaving a zone must not evict the other one from it.

        The recomputation drops every zone company before re-deriving them, so
        a product co-owned by two shops of the same zone is the case where a
        naive "remove the old zone" would silently take the second shop's
        catalogue out of its own shop.
        """
        neighbour = self.env["res.company"].create(
            {"name": "Zone Test Neighbour", "commercial_zone": "guanarteme"}
        )
        product = self._product(self.shop | neighbour)

        self.shop.commercial_zone = "tamaraceite"

        product.invalidate_recordset(["company_ids"])
        self.assertIn(self.zone_tamaraceite, product.company_ids)
        self.assertIn(
            self.zone_guanarteme,
            product.company_ids,
            "the neighbour is still in Guanarteme and still sells this",
        )

    def test_users_follow_the_zone_too(self):
        user = self.env["res.users"].create(
            {
                "name": "Zone Test Merchant",
                "login": "zone_test_merchant",
                "company_id": self.shop.id,
                "company_ids": [(6, 0, (self.shop | self.platform).ids)],
            }
        )
        self.assertIn(self.zone_guanarteme, user.company_ids)

        self.shop.commercial_zone = "tamaraceite"

        user.invalidate_recordset(["company_ids"])
        self.assertIn(self.zone_tamaraceite, user.company_ids)
        self.assertNotIn(self.zone_guanarteme, user.company_ids)

    def test_the_staff_of_a_zone_keep_their_own_company(self):
        """The people who work FOR a zone are the edge case of the rule.

        Their own company IS a zone company, and the recomputation drops zone
        companies before re-deriving them -- so without a floor they would be
        stripped of the company they are logged into.
        """
        staff = self.env["res.users"].create(
            {
                "name": "Zone Test Staff",
                "login": "zone_test_staff",
                "company_id": self.zone_guanarteme.id,
                "company_ids": [(6, 0, self.zone_guanarteme.ids)],
            }
        )
        staff._apply_zone_companies()
        self.assertIn(self.zone_guanarteme, staff.company_ids)

    def test_the_zone_alone_does_not_satisfy_the_ownership_guard(self):
        """A zone rides along; it never substitutes for the shop.

        Merchants belong to their zone company now, which is what would let
        "keep at least one of your own companies" be satisfied by the zone
        alone -- and a product owned by the zone but not by the shop is out of
        the shop's own catalogue, which is the exact problem the guard exists
        to prevent.
        """
        merchant = self.env["res.users"].create(
            {
                "name": "Zone Guard Merchant",
                "login": "zone_guard_merchant",
                "company_id": self.shop.id,
                "company_ids": [(6, 0, (self.shop | self.zone_guanarteme).ids)],
            }
        )
        guarded = merchant.with_context(test_multi_company_field_visible=True)
        self.assertEqual(
            self.env["product.template"]
            .with_user(guarded)
            ._guard_own_companies(),
            self.shop,
            "only the merchant's real shop may count as theirs",
        )

    def test_running_it_twice_changes_nothing(self):
        """Idempotent, because the backfill will run over live data."""
        product = self._product(self.shop | self.platform)
        first = product.company_ids

        self.assertFalse(
            product._apply_zone_companies(),
            "a record that is already right must not be written again",
        )
        self.assertEqual(product.company_ids, first)
