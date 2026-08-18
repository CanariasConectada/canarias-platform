# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import tagged
from odoo.tests.common import TransactionCase

from odoo.addons.website_sale_comparison_canarias.models.website import (
    SCOPE_ALL,
    SCOPE_OTHER_ZONE,
    SCOPE_SHOP,
    SCOPE_ZONE,
)


@tagged("post_install", "-at_install")
class TestCompareScopes(TransactionCase):
    """Compare against what, exactly.

    Asked for on 2026-08-16: a modal on the product page that compares
    against the whole of Canarias Conectada, the current commercial zone,
    another one, or the same shop.

    Every one of those four is a site the platform already serves, so the
    tests here are about resolving the right SITE. What that site is allowed
    to show is `website_sale_marketplace`'s business, and reusing it is the
    reason this endpoint is safe to leave open.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Creating ANY company on this platform trips website_sale_collect's
        # "the delivery method and a warehouse must share the same company".
        # The database holds no mismatched row -- the mismatch is produced
        # during the create itself, when the new company's warehouse meets an
        # in_store delivery method that is not its own. It blocks onboarding a
        # merchant, not just this test, and it is reported separately.
        #
        # Held open for the whole class rather than the fixtures alone: the
        # pending recompute is flushed again at the start of every test.
        #
        # Only when website_sale_collect is actually installed: on the clean
        # CI database the module (and its constraint) does not exist, and
        # patching a missing attribute aborts the whole class in setUpClass.
        carrier_cls = type(cls.env["delivery.carrier"])
        if hasattr(carrier_cls, "_check_warehouses_have_same_company"):
            cls.startClassPatcher(
                patch.object(
                    carrier_cls,
                    "_check_warehouses_have_same_company",
                    lambda self: None,
                )
            )
        # The marketplace backfill is `website_sale_marketplace`'s business and
        # is tested there. Here it would link the whole catalogue -- 1576
        # products on a copy of production -- to a throwaway company, for no
        # assertion.
        cls.startClassPatcher(
            patch.object(
                type(cls.env["website"]),
                "_sync_marketplace_products",
                lambda self: None,
            )
        )
        # The fixtures below ARE the platform for the length of this class.
        # On a copy of production the real portal is website 1 and the real
        # zone shops are 12, 13 and 14, and every helper here answers with the
        # lowest id it finds -- correctly, and never with the fixtures.
        cls.env["website"].sudo().search([("is_marketplace", "=", True)]).write(
            {"is_marketplace": False}
        )
        cls.portal_company = cls.env["res.company"].create({"name": "Portal Test"})
        cls.portal = cls.env["website"].create(
            {
                "name": "Portal Test",
                "company_id": cls.portal_company.id,
                "is_marketplace": True,
            }
        )
        cls.zone_a_company = cls.env["res.company"].create(
            {"name": "Zona A Test", "commercial_zone": "guanarteme"}
        )
        cls.zone_a = cls.env["website"].create(
            {
                "name": "Zona A Test",
                "company_id": cls.zone_a_company.id,
                "is_marketplace": True,
                "marketplace_zone": "guanarteme",
            }
        )
        cls.zone_b_company = cls.env["res.company"].create(
            {"name": "Zona B Test", "commercial_zone": "tamaraceite"}
        )
        cls.zone_b = cls.env["website"].create(
            {
                "name": "Zona B Test",
                "company_id": cls.zone_b_company.id,
                "is_marketplace": True,
                "marketplace_zone": "tamaraceite",
            }
        )
        cls.shop_company = cls.env["res.company"].create(
            {"name": "Tienda Test", "commercial_zone": "guanarteme"}
        )
        cls.shop = cls.env["website"].create(
            {"name": "Tienda Test", "company_id": cls.shop_company.id}
        )
        # A shop in no neighbourhood, for the assertions that must not have
        # the platform's real zone companies added to their product.
        cls.plain_shop_company = cls.env["res.company"].create(
            {"name": "Tienda Sin Zona Test"}
        )
        cls.plain_shop = cls.env["website"].create(
            {"name": "Tienda Sin Zona Test", "company_id": cls.plain_shop_company.id}
        )
        cls.plain_product = cls.env["product.template"].create(
            {
                "name": "Compare Scope Plain Product",
                "is_published": True,
                "list_price": 10.0,
                "company_ids": [
                    (6, 0, (cls.plain_shop_company | cls.portal_company).ids)
                ],
            }
        )
        # `res.company.website_id` is stored with NO @api.depends: core
        # computes it when the company is created and never again, so a
        # website created afterwards never reaches it. Production carries
        # it on all 216 companies; fixtures have to say so themselves.
        cls.portal_company.website_id = cls.portal
        cls.zone_a_company.website_id = cls.zone_a
        cls.zone_b_company.website_id = cls.zone_b
        cls.shop_company.website_id = cls.shop
        cls.plain_shop_company.website_id = cls.plain_shop

        cls.product = cls.env["product.template"].create(
            {
                "name": "Compare Scope Product",
                "is_published": True,
                "list_price": 10.0,
                "company_ids": [
                    (
                        6,
                        0,
                        (
                            cls.shop_company | cls.portal_company | cls.zone_a_company
                        ).ids,
                    )
                ],
            }
        )

    # ------------------------------------------------------------------
    # Resolving a scope to a site
    # ------------------------------------------------------------------
    def test_the_whole_platform_is_the_portal_shop(self):
        """Found by what it is, not by id.

        Company 1 owns two websites on this platform -- the portal and the
        Admin Portal -- so `company.website_id` is ambiguous and "marketplace
        with no zone" is the only honest definition.
        """
        self.assertEqual(
            self.shop._comparison_scope_website(SCOPE_ALL),
            self.portal,
        )

    def test_my_zone_is_the_zone_of_the_shop_i_am_standing_in(self):
        self.assertEqual(
            self.shop._comparison_scope_website(SCOPE_ZONE),
            self.zone_a,
        )

    def test_another_zone_is_the_one_that_was_asked_for(self):
        self.assertEqual(
            self.shop._comparison_scope_website(SCOPE_OTHER_ZONE, zone="tamaraceite"),
            self.zone_b,
        )

    def test_the_same_shop_means_the_shop_that_sells_this_product(self):
        """Not the site the visitor happens to be on.

        The question gets asked on the portal, where every shop's products
        are mixed together, and "solo en esta tienda" there has to mean the
        merchant -- which is why the marketplace companies are subtracted
        from `company_ids` rather than the current website used.

        Built on a shop with no neighbourhood so the assertion is about the
        subtraction and nothing else: `zone_company_ownership` adds the zone
        company to every product of a merchant that has one, and on a copy of
        production those zone companies are already there.
        """
        self.assertEqual(
            self.portal._comparison_scope_website(
                SCOPE_SHOP, product=self.plain_product
            ),
            self.plain_shop,
        )

    def test_an_unknown_zone_resolves_to_nothing_rather_than_to_something(self):
        self.assertFalse(
            self.shop._comparison_scope_website(SCOPE_OTHER_ZONE, zone="atlantis")
        )

    def test_outside_the_zone_is_answered_by_the_portal(self):
        """One click, no zone named: the portal's catalogue minus the
        product's neighbourhood (the subtraction is the controller's)."""
        self.assertEqual(
            self.shop._comparison_scope_website(
                SCOPE_OTHER_ZONE, product=self.product
            ),
            self.portal,
        )

    def test_outside_of_no_zone_resolves_to_nothing(self):
        """A product in no neighbourhood has no outside."""
        self.assertFalse(
            self.portal._comparison_scope_website(
                SCOPE_OTHER_ZONE, product=self.plain_product
            )
        )

    # ------------------------------------------------------------------
    # The product's zone
    # ------------------------------------------------------------------
    def test_the_zone_of_a_product_is_the_zone_of_its_merchant(self):
        """Wherever the visitor is standing, including the portal."""
        self.assertEqual(
            self.portal._comparison_product_zone(self.product), "guanarteme"
        )

    def test_a_product_with_no_zone_falls_back_to_the_websites_zone(self):
        """So a zone shop keeps answering with itself."""
        self.assertEqual(
            self.zone_b._comparison_product_zone(self.plain_product), "tamaraceite"
        )

    def test_a_product_with_no_zone_on_the_portal_has_none(self):
        """The merchant's default "canarias" means "no neighbourhood", and
        the portal has none to fall back to."""
        self.assertFalse(self.portal._comparison_product_zone(self.plain_product))

    def test_outside_zone_companies_are_the_companies_of_the_products_zone(self):
        """The exact list ``website._zone_company_ids`` answers with:
        every company of the zone, the product's own merchant included."""
        excluded = self.portal._comparison_outside_zone_company_ids(self.product)
        self.assertIn(self.zone_a_company.id, excluded)
        self.assertIn(self.shop_company.id, excluded)
        self.assertNotIn(self.zone_b_company.id, excluded)

    def test_outside_zone_companies_of_a_zoneless_product_are_none(self):
        self.assertEqual(
            self.portal._comparison_outside_zone_company_ids(self.plain_product), []
        )

    def test_an_unknown_scope_resolves_to_nothing(self):
        self.assertFalse(self.shop._comparison_scope_website("everything"))

    # ------------------------------------------------------------------
    # What gets offered where
    # ------------------------------------------------------------------
    def _keys(self, website, product=None):
        return [scope["key"] for scope in website._comparison_scopes(product)]

    def test_a_shop_offers_all_four(self):
        keys = self._keys(self.shop, self.product)
        self.assertEqual(keys, [SCOPE_ALL, SCOPE_ZONE, SCOPE_OTHER_ZONE, SCOPE_SHOP])

    def test_the_portal_offers_the_zone_of_the_product(self):
        """The zone is the PRODUCT's, not the website's.

        The portal belongs to no neighbourhood, but a Guanarteme product seen
        there still has one -- and that is exactly where the visitor asks the
        question, because the portal is where every shop's products mix.
        """
        scopes = self.portal._comparison_scopes(self.product)
        keys = [scope["key"] for scope in scopes]
        self.assertIn(SCOPE_ZONE, keys)
        zone_scope = next(s for s in scopes if s["key"] == SCOPE_ZONE)
        self.assertIn(self.zone_a.name, zone_scope["label"])

    def test_without_a_product_the_portal_still_offers_no_zone(self):
        """No product and no neighbourhood of its own: nothing to scope to."""
        self.assertNotIn(SCOPE_ZONE, self._keys(self.portal))
        self.assertNotIn(SCOPE_OTHER_ZONE, self._keys(self.portal))

    def test_a_product_in_no_zone_offers_no_zone_scopes_on_the_portal(self):
        """Outside of nothing is everything, and "everything" already has
        its own scope."""
        keys = self._keys(self.portal, self.plain_product)
        self.assertNotIn(SCOPE_ZONE, keys)
        self.assertNotIn(SCOPE_OTHER_ZONE, keys)

    def test_a_zone_shop_does_not_offer_its_own_zone_twice(self):
        scopes = self.zone_a._comparison_scopes(self.product)
        others = next(s for s in scopes if s["key"] == SCOPE_OTHER_ZONE)
        self.assertNotIn(
            "guanarteme",
            [zone["key"] for zone in others["zones"]],
            "the zone you are already in is not another zone",
        )

    def test_without_a_product_there_is_no_this_shop(self):
        self.assertNotIn(SCOPE_SHOP, self._keys(self.portal))

    def test_it_opens_on_the_narrowest_scope_the_visitor_is_inside(self):
        """The shop's own shelf first; the whole platform is one click away.

        Opening on 1573 products would have been technically correct and
        useless.
        """
        self.assertEqual(self.shop._comparison_default_scope(self.product), SCOPE_SHOP)
        self.assertEqual(self.portal._comparison_default_scope(), SCOPE_ALL)
        self.assertEqual(self.zone_a._comparison_default_scope(), SCOPE_ZONE)
