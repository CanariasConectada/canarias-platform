# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.zone_company_ownership.models.res_company import SKIP_CONTEXT


@tagged("post_install", "-at_install")
class TestZoneCompanyOwnership(TransactionCase):
    """A merchant's catalogue follows the merchant's neighbourhood.

    Asked for on 2026-08-14: "la empresa que se va a agregar también es de la
    zona comercial a la que la empresa pertenece, si a la empresa le cambiamos
    la zona comercial, pues los productos y usuarios también deben
    actualizarse".

    The user half of that was walked back on 2026-08-15: giving the merchant's
    ACCOUNT the zone company handed every merchant of a neighbourhood read and
    write access to every other one's products and contacts. The catalogue
    still follows the zone; the person does not.
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
        """ "si no está en ninguna, pues sólo estará con canarias conectada"."""
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

    def test_a_merchant_never_keeps_a_zone_company(self):
        """The catalogue goes into the zone; the person does not.

        ``res.users.company_ids`` is what every multi-company record rule
        reads, so a zone company there is not "my shop is in the zone shop",
        it is "I may read and write everything the zone owns" -- which is
        every other merchant of the neighbourhood.
        """
        user = self.env["res.users"].create(
            {
                "name": "Zone Test Merchant",
                "login": "zone_test_merchant",
                "company_id": self.shop.id,
                "company_ids": [
                    (6, 0, (self.shop | self.platform | self.zone_guanarteme).ids)
                ],
            }
        )

        self.assertNotIn(self.zone_guanarteme, user.company_ids)
        self.assertEqual(user.company_ids, self.shop | self.platform)

    def test_a_zone_company_added_by_hand_is_taken_back_off(self):
        """Self-healing, because the hole can be reopened from the user form."""
        user = self.env["res.users"].create(
            {
                "name": "Zone Test Rehired",
                "login": "zone_test_rehired",
                "company_id": self.shop.id,
                "company_ids": [(6, 0, self.shop.ids)],
            }
        )

        user.company_ids = [(4, self.zone_tamaraceite.id)]

        user.invalidate_recordset(["company_ids"])
        self.assertEqual(user.company_ids, self.shop)

    def test_the_staff_of_a_zone_keep_their_own_company(self):
        """The people who work FOR a zone are the edge case of the rule.

        Their own company IS a zone company, so the guard that strips zone
        companies would leave them logged into a company they are not allowed
        into -- which core rejects outright.
        """
        staff = self.env["res.users"].create(
            {
                "name": "Zone Test Staff",
                "login": "zone_test_staff",
                "company_id": self.zone_guanarteme.id,
                "company_ids": [(6, 0, self.zone_guanarteme.ids)],
            }
        )
        staff._drop_zone_companies()
        self.assertIn(self.zone_guanarteme, staff.company_ids)

    def test_an_administrator_keeps_every_company(self):
        """The only other exemption, and it is ``group_system``, not
        ``group_multi_company``: the merchants hold that one.

        The real administrator is used rather than a freshly built one because
        ``base_user_role`` reverts group writes made directly on a user, so a
        fixture "admin" would silently not be one.
        """
        admin = self.env.ref("base.user_admin")
        admin.with_context(**{SKIP_CONTEXT: True}).company_ids = [
            (4, self.zone_guanarteme.id)
        ]

        admin._drop_zone_companies()

        self.assertIn(self.zone_guanarteme, admin.company_ids)

    def test_the_zone_alone_does_not_satisfy_the_ownership_guard(self):
        """A zone rides along; it never substitutes for the shop.

        The user-side guard is the first line and the ownership guard is the
        second: should a zone company ever reach a merchant's account again,
        "keep at least one of your own companies" must still not accept the
        zone alone -- a product owned by the zone but not by the shop is out of
        the shop's own catalogue, which is the exact problem the guard exists
        to prevent.
        """
        # Built with the guard suspended on purpose: the point of this test is
        # what the OWNERSHIP guard does when a zone company is present, and
        # ``res.users`` now takes it off before anything else can look at it.
        merchant = (
            self.env["res.users"]
            .with_context(**{SKIP_CONTEXT: True})
            .create(
                {
                    "name": "Zone Guard Merchant",
                    "login": "zone_guard_merchant",
                    "company_id": self.shop.id,
                    "company_ids": [(6, 0, (self.shop | self.zone_guanarteme).ids)],
                }
            )
        )
        guarded = merchant.with_context(test_multi_company_field_visible=True)
        self.assertEqual(
            self.env["product.template"].with_user(guarded)._guard_own_companies(),
            self.shop,
            "only the merchant's real shop may count as theirs",
        )

    def test_a_delivery_method_never_gets_a_zone(self):
        """The exclusion that keeps 150 live delivery methods working.

        ``delivery.carrier.company_id`` is ``related='product_id.company_id',
        store=True`` — a STORED field following one that
        ``multi.company.abstract`` computes from the active companies. Give the
        product behind a carrier a second owner and that stored company starts
        depending on who is looking, which
        ``website_sale_collect._check_warehouses_have_same_company`` then
        rejects. It already cost one aborted migration run.

        Live, every carrier product owns exactly one company. This is what
        keeps it that way.
        """
        product = self._product(self.shop.ids and self.shop or self.platform)
        carrier = self.env["delivery.carrier"].create(
            {
                "name": "Zone Test Carrier",
                "product_id": product.product_variant_id.id,
            }
        )
        self.assertTrue(carrier)

        candidates = product._zone_sync_candidates()

        self.assertNotIn(
            product,
            candidates,
            "a product backing a delivery method must stay out of the sweep",
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


@tagged("post_install", "-at_install")
class TestZonePartnerOwnership(TransactionCase):
    """A merchant's contacts follow the merchant's neighbourhood too.

    Asked for on 2026-09-02: "verifiques que se esten asignando tanto los
    contactos como los productos a las zonas comerciales que les
    correspondan [...] la idea es poder agrupar tambien por zona comercial".
    Same contract as the catalogue: the contact GAINS the zone company, and
    a zone change re-derives it from the real owners.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.zone_guanarteme = cls.env["res.company"].create(
            {"name": "Zone P Guanarteme", "zone_company_key": "guanarteme"}
        )
        cls.zone_tamaraceite = cls.env["res.company"].create(
            {"name": "Zone P Tamaraceite", "zone_company_key": "tamaraceite"}
        )
        cls.platform = cls.env.ref("base.main_company")
        cls.shop = cls.env["res.company"].create(
            {"name": "Zone P Shop", "commercial_zone": "guanarteme"}
        )

    def _partner(self, owners):
        return self.env["res.partner"].create(
            {"name": "Zone Test Contact", "company_ids": [(6, 0, owners.ids)]}
        )

    def test_a_new_contact_joins_its_zone(self):
        partner = self._partner(self.shop)
        self.assertIn(self.zone_guanarteme, partner.company_ids)
        self.assertIn(self.shop, partner.company_ids)

    def test_moving_the_shop_moves_its_address_book(self):
        partner = self._partner(self.shop)

        self.shop.commercial_zone = "tamaraceite"

        partner.invalidate_recordset(["company_ids"])
        self.assertIn(self.zone_tamaraceite, partner.company_ids)
        self.assertNotIn(
            self.zone_guanarteme,
            partner.company_ids,
            "a shop that moved must take its contacts out of the zone it left",
        )

    def test_a_global_contact_stays_global(self):
        """No owners means visible everywhere. The sync must not narrow it."""
        partner = self.env["res.partner"].create(
            {"name": "Zone Test Global", "company_ids": [(5, 0, 0)]}
        )
        self.assertFalse(partner.company_ids)
        self.assertFalse(partner.zone_company_ids)

    def test_the_zones_own_card_keeps_its_company(self):
        """A contact whose own company IS the zone must not be stripped."""
        partner = self._partner(self.zone_guanarteme)
        self.assertEqual(partner.company_ids, self.zone_guanarteme)

    def test_zone_company_ids_reads_only_the_zone(self):
        """The group-by field carries the zone alone, never the shop.

        Key-based assertions on purpose: the test database is a production
        copy whose REAL zone companies share the fixtures' zone_company_key,
        and the sync correctly derives every company standing for the key.
        """
        partner = self._partner(self.shop | self.platform)
        self.assertIn(self.zone_guanarteme, partner.zone_company_ids)
        self.assertTrue(
            all(c.zone_company_key for c in partner.zone_company_ids),
            "only zone companies may appear in the group-by field",
        )
        self.assertNotIn(self.shop, partner.zone_company_ids)
        self.assertNotIn(self.platform, partner.zone_company_ids)

        self.shop.commercial_zone = "tamaraceite"

        partner.invalidate_recordset(["company_ids", "zone_company_ids"])
        self.assertIn(self.zone_tamaraceite, partner.zone_company_ids)
        self.assertFalse(
            partner.zone_company_ids.filtered(
                lambda c: c.zone_company_key == "guanarteme"
            ),
            "the old zone must fall out entirely",
        )

    def test_products_carry_the_groupby_field_too(self):
        product = self.env["product.template"].create(
            {"name": "Zone Test Product", "company_ids": [(6, 0, self.shop.ids)]}
        )
        self.assertIn(self.zone_guanarteme, product.zone_company_ids)
        self.assertTrue(
            all(c.zone_company_key for c in product.zone_company_ids)
        )

    def test_a_users_card_gains_the_zone_without_the_user(self):
        """The contact goes into the zone; the account still does not."""
        user = self.env["res.users"].create(
            {
                "name": "Zone Test Merchant",
                "login": "zone-partner-merchant@example.invalid",
                "company_id": self.shop.id,
                "company_ids": [(6, 0, self.shop.ids)],
            }
        )
        self.assertIn(self.zone_guanarteme, user.partner_id.company_ids)
        self.assertNotIn(self.zone_guanarteme, user.company_ids)
