# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale_comparison_canarias.controllers.main import (
    CANDIDATE_LIMIT,
)


@tagged("post_install", "-at_install")
class TestCompareCandidates(HttpCase):
    """What the picker is allowed to offer an anonymous visitor.

    The endpoint is public, so the interesting assertions are the negative
    ones: it must not hand out an unpublished product, and it must not reach
    across websites. Both come from reusing ``website.sale_product_domain()``
    rather than writing a domain here -- these tests are what proves that
    reuse actually holds.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.website = cls.env["website"].browse(1)
        # On a copy of production website 1 already IS the portal; on a bare
        # database no marketplace exists and every scope would resolve to
        # nothing. The truncation and search assertions need a shop to answer,
        # so the answering site steps up only when nobody else does.
        if not cls.website._comparison_portal_website():
            cls.startClassPatcher(
                patch.object(
                    type(cls.env["website"]),
                    "_sync_marketplace_products",
                    lambda self: None,
                )
            )
            cls.website.is_marketplace = True
        cls.category = cls.env["product.public.category"].create(
            {"name": "Compare Test Category"}
        )
        cls.published = cls.env["product.template"].create(
            {
                "name": "Compare Test Published",
                "is_published": True,
                "list_price": 10.0,
                "public_categ_ids": [(6, 0, cls.category.ids)],
            }
        )
        cls.other = cls.env["product.template"].create(
            {
                "name": "Compare Test Other",
                "is_published": True,
                "list_price": 20.0,
                "public_categ_ids": [(6, 0, cls.category.ids)],
            }
        )
        cls.unpublished = cls.env["product.template"].create(
            {"name": "Compare Test Unpublished", "is_published": False}
        )
        # One more product than the cap, all sorting BEFORE the needle
        # ("Filler" < "Needle" in any collation), so the needle is provably
        # beyond the alphabetical first page whatever else the database holds.
        cls.env["product.template"].create(
            [
                {
                    "name": "Compare Query Filler %03d" % index,
                    "is_published": True,
                    "list_price": 5.0,
                }
                for index in range(CANDIDATE_LIMIT + 1)
            ]
        )
        cls.needle = cls.env["product.template"].create(
            {
                "name": "Compare Query Needle",
                "is_published": True,
                "list_price": 5.0,
            }
        )

    def _candidates(self, template_id, **params):
        return self.opener.post(
            self.base_url() + "/shop/compare/candidates",
            json={
                "params": {"product_template_id": template_id, **params},
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
            },
        ).json()["result"]

    def test_a_scope_nobody_offered_falls_back_instead_of_being_obeyed(self):
        """A query string belongs to whoever is holding the address bar."""
        data = self._candidates(self.published.id, scope="everything")
        self.assertIn(data["scope"], {entry["key"] for entry in data["scopes"]})

    def test_a_zone_that_does_not_exist_falls_back_too(self):
        data = self._candidates(self.published.id, scope="other_zone", zone="atlantis")
        self.assertIn(data["scope"], {entry["key"] for entry in data["scopes"]})
        self.assertTrue(data["products"] or not data["scopes"])

    def test_an_unpublished_product_is_never_offered(self):
        names = [p["name"] for p in self._candidates(self.published.id)["products"]]
        self.assertNotIn("Compare Test Unpublished", names)

    def test_the_product_being_compared_is_not_in_its_own_list(self):
        ids = [p["id"] for p in self._candidates(self.published.id)["products"]]
        self.assertNotIn(self.published.id, ids)

    def test_the_categories_of_the_clicked_product_come_back(self):
        """So the modal can open already narrowed to "things like this one"."""
        data = self._candidates(self.published.id)
        self.assertIn(self.category.id, data["current_category_ids"])

    def test_facets_only_list_categories_that_have_candidates(self):
        """A filter that returns nothing is worse than no filter."""
        data = self._candidates(self.published.id)
        offered = {c["id"] for c in data["categories"]}
        with_candidates = set()
        for product in data["products"]:
            with_candidates.update(product["category_ids"])
        self.assertEqual(offered, with_candidates)

    def test_every_candidate_carries_what_the_modal_draws(self):
        for product in self._candidates(self.published.id)["products"][:5]:
            for key in ("id", "variant_id", "name", "price", "image_url", "url"):
                self.assertIn(key, product)

    def test_the_search_reaches_past_the_cap(self):
        """The pool is truncated alphabetically; the query must not be.

        With ``CANDIDATE_LIMIT + 1`` fillers sorting before it, the needle
        can never be on the first page -- and one typed word must still find
        it, because the query is a server-side leaf AND-ed onto the same
        website-derived domain, not a filter over the truncated page.
        """
        without = self._candidates(self.published.id)
        self.assertNotIn(
            "Compare Query Needle", [p["name"] for p in without["products"]]
        )
        with_query = self._candidates(self.published.id, query="Query Needle")
        self.assertEqual(
            [p["name"] for p in with_query["products"]], ["Compare Query Needle"]
        )
        self.assertEqual(with_query["total"], 1)

    def test_the_total_tells_the_truth_about_the_truncation(self):
        """So the modal can say "showing 120 of N" instead of lying by
        omission."""
        data = self._candidates(self.published.id)
        self.assertEqual(len(data["products"]), CANDIDATE_LIMIT)
        self.assertEqual(data["limit"], CANDIDATE_LIMIT)
        self.assertGreater(data["total"], len(data["products"]))

    def test_the_query_still_cannot_reach_an_unpublished_product(self):
        """Searching narrows the safe domain; it never widens it."""
        data = self._candidates(self.published.id, query="Compare Test Unpublished")
        self.assertEqual(data["products"], [])
        self.assertEqual(data["total"], 0)


@tagged("post_install", "-at_install")
class TestCompareCandidatesZones(HttpCase):
    """The zone scopes, asked over HTTP the way the portal asks them.

    The zone is the PRODUCT's: a Guanarteme product seen on the portal offers
    "my commercial zone: Guanarteme", and "outside my commercial zone" is the
    portal's own catalogue minus that neighbourhood -- both still answered
    through a website's ``sale_product_domain()``, never a hand-written
    visibility domain.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Same two patches as the scope tests, for the same reasons: creating
        # ANY company trips website_sale_collect's warehouse/company check,
        # and the marketplace backfill would link the whole catalogue to the
        # fixture sites for no assertion.
        cls.startClassPatcher(
            patch.object(
                type(cls.env["delivery.carrier"]),
                "_check_warehouses_have_same_company",
                lambda self: None,
            )
        )
        cls.startClassPatcher(
            patch.object(
                type(cls.env["website"]),
                "_sync_marketplace_products",
                lambda self: None,
            )
        )
        # Website 1 is the one that answers localhost, so IT plays the
        # portal; the real marketplaces (if this is a copy of production)
        # step aside so every helper resolves to the fixtures.
        cls.env["website"].sudo().search([("is_marketplace", "=", True)]).write(
            {"is_marketplace": False}
        )
        cls.portal = cls.env["website"].browse(1)
        cls.portal.is_marketplace = True
        cls.zone_company = cls.env["res.company"].create(
            {"name": "Zona HTTP Test", "commercial_zone": "guanarteme"}
        )
        cls.zone_site = cls.env["website"].create(
            {
                "name": "Zona HTTP Test",
                "company_id": cls.zone_company.id,
                "is_marketplace": True,
                "marketplace_zone": "guanarteme",
                "domain": "https://zone-http.example",
            }
        )
        cls.merchant = cls.env["res.company"].create(
            {"name": "Comercio HTTP Test", "commercial_zone": "guanarteme"}
        )
        cls.merchant_site = cls.env["website"].create(
            {
                "name": "Comercio HTTP Test",
                "company_id": cls.merchant.id,
                "domain": "https://merchant-http.example",
            }
        )
        # `res.company.website_id` is stored with no @api.depends: fixtures
        # have to say so themselves (see test_compare_scopes).
        cls.zone_company.website_id = cls.zone_site
        cls.merchant.website_id = cls.merchant_site
        # The portal company rides along on every product exactly as the
        # (patched-out) marketplace backfill would have put it there: without
        # it the portal shop cannot see a company-owned product at all.
        cls.clicked = cls.env["product.template"].create(
            {
                "name": "Zone HTTP Clicked",
                "is_published": True,
                "list_price": 10.0,
                "company_ids": [(6, 0, (cls.merchant | cls.portal.company_id).ids)],
            }
        )
        cls.same_zone = cls.env["product.template"].create(
            {
                "name": "Zone HTTP Same Zone",
                "is_published": True,
                "list_price": 11.0,
                "company_ids": [(6, 0, (cls.merchant | cls.portal.company_id).ids)],
            }
        )
        cls.elsewhere_company = cls.env["res.company"].create(
            {"name": "Comercio Lejano HTTP Test", "commercial_zone": "tamaraceite"}
        )
        cls.elsewhere = cls.env["product.template"].create(
            {
                "name": "Zone HTTP Elsewhere",
                "is_published": True,
                "list_price": 12.0,
                "company_ids": [
                    (6, 0, (cls.elsewhere_company | cls.portal.company_id).ids)
                ],
            }
        )

    def _candidates(self, template_id, **params):
        return self.opener.post(
            self.base_url() + "/shop/compare/candidates",
            json={
                "params": {"product_template_id": template_id, **params},
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
            },
        ).json()["result"]

    def test_the_portal_offers_the_products_zone(self):
        data = self._candidates(self.clicked.id, scope="zone")
        self.assertEqual(data["scope"], "zone")
        zone_scope = next(s for s in data["scopes"] if s["key"] == "zone")
        self.assertIn(self.zone_site.name, zone_scope["label"])

    def test_the_products_zone_answers_with_that_zones_shop(self):
        """Searched by name: on a copy of production the neighbourhood
        holds more than the 120-product page, and a fixture named "Zone..."
        sorts far beyond it."""
        names = [
            p["name"]
            for p in self._candidates(
                self.clicked.id, scope="zone", query="Zone HTTP"
            )["products"]
        ]
        self.assertIn("Zone HTTP Same Zone", names)
        self.assertNotIn("Zone HTTP Elsewhere", names)

    def test_outside_the_zone_excludes_the_zones_products(self):
        data = self._candidates(self.clicked.id, scope="other_zone", query="Zone HTTP")
        self.assertEqual(data["scope"], "other_zone")
        names = [p["name"] for p in data["products"]]
        self.assertNotIn("Zone HTTP Same Zone", names)
        self.assertIn("Zone HTTP Elsewhere", names)
