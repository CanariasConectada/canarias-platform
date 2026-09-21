# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from unittest.mock import patch

from odoo.fields import Domain
from odoo.tests import HttpCase, tagged

from odoo.addons.website_sale_comparison_canarias.controllers.main import (
    CANDIDATE_LIMIT,
    MAX_CLIENT_IDS,
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
        Category = cls.env["product.public.category"]
        cls.category = Category.create({"name": "Compare Test Category"})
        cls.child_category = Category.create(
            {"name": "Compare Test Child Category", "parent_id": cls.category.id}
        )
        cls.other_category = Category.create({"name": "Compare Test Other Category"})
        cls.second_category = Category.create({"name": "Compare Test Second Category"})
        # Only ever worn by the unpublished product: a category nobody may
        # see a product of, so it must never become a chip nor a filter.
        cls.hidden_category = Category.create({"name": "Compare Test Hidden Category"})
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
        # In the clicked product's own category on purpose: the default
        # filter must not be what keeps it out.
        cls.unpublished = cls.env["product.template"].create(
            {
                "name": "Compare Test Unpublished",
                "is_published": False,
                "public_categ_ids": [(6, 0, (cls.category | cls.hidden_category).ids)],
            }
        )
        cls.in_child = cls.env["product.template"].create(
            {
                "name": "Compare Test Child",
                "is_published": True,
                "list_price": 30.0,
                "public_categ_ids": [(6, 0, cls.child_category.ids)],
            }
        )
        cls.elsewhere = cls.env["product.template"].create(
            {
                "name": "Compare Test Elsewhere",
                "is_published": True,
                "list_price": 40.0,
                "public_categ_ids": [(6, 0, cls.other_category.ids)],
            }
        )
        cls.in_second = cls.env["product.template"].create(
            {
                "name": "Compare Test Second",
                "is_published": True,
                "list_price": 50.0,
                "public_categ_ids": [(6, 0, cls.second_category.ids)],
            }
        )
        cls.multi = cls.env["product.template"].create(
            {
                "name": "Compare Test Multi",
                "is_published": True,
                "list_price": 60.0,
                "public_categ_ids": [(6, 0, (cls.category | cls.second_category).ids)],
            }
        )
        # More products than the cap, all sorting BEFORE the needle
        # ("Filler" < "Needle" in any collation), so the needle is provably
        # beyond the alphabetical first page whatever else the database holds.
        # They share a category of their own, so that clicking one of them
        # leaves a SAME-CATEGORY list that is itself longer than the cap.
        cls.filler_category = Category.create({"name": "Compare Test Filler Category"})
        cls.fillers = cls.env["product.template"].create(
            [
                {
                    "name": "Compare Query Filler %03d" % index,
                    "is_published": True,
                    "list_price": 5.0,
                    "public_categ_ids": [(6, 0, cls.filler_category.ids)],
                }
                for index in range(CANDIDATE_LIMIT + 2)
            ]
        )
        cls.needle = cls.env["product.template"].create(
            {
                "name": "Compare Query Needle",
                "is_published": True,
                "list_price": 5.0,
            }
        )

    def _post(self, template_id, **params):
        return self.opener.post(
            self.base_url() + "/shop/compare/candidates",
            json={
                "params": {"product_template_id": template_id, **params},
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
            },
        )

    def _candidates(self, template_id, **params):
        return self._post(template_id, **params).json()["result"]

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
        """A filter that returns nothing is worse than no filter.

        Asked with the same category unticked and narrowed by name, so the
        page holds every candidate of the query and the two sets can be
        compared exactly. The clicked product's own category is step 2's
        business and is never repeated among the others.
        """
        data = self._candidates(
            self.published.id, same_category_ids=[], query="Compare Test"
        )
        offered = {c["id"] for c in data["categories"]}
        with_candidates = set()
        for product in data["products"]:
            with_candidates.update(product["category_ids"])
        self.assertEqual(offered, with_candidates - {self.category.id})
        self.assertNotIn(self.hidden_category.id, offered)

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

        The same category is unticked throughout: the fillers and the needle
        have none, and this is about the cap, not about the categories.
        """
        without = self._candidates(self.published.id, same_category_ids=[])
        self.assertNotIn(
            "Compare Query Needle", [p["name"] for p in without["products"]]
        )
        with_query = self._candidates(
            self.published.id, same_category_ids=[], query="Query Needle"
        )
        self.assertEqual(
            [p["name"] for p in with_query["products"]], ["Compare Query Needle"]
        )
        self.assertEqual(with_query["total"], 1)

    def test_the_total_tells_the_truth_about_the_truncation(self):
        """So the modal can say "showing 120 of N" instead of lying by
        omission."""
        data = self._candidates(self.published.id, same_category_ids=[])
        self.assertEqual(len(data["products"]), CANDIDATE_LIMIT)
        self.assertEqual(data["limit"], CANDIDATE_LIMIT)
        self.assertGreater(data["total"], len(data["products"]))

    def test_the_query_still_cannot_reach_an_unpublished_product(self):
        """Searching narrows the safe domain; it never widens it."""
        for same_category_ids in (None, []):
            data = self._candidates(
                self.published.id,
                query="Compare Test Unpublished",
                same_category_ids=same_category_ids,
            )
            self.assertEqual(data["products"], [])
            self.assertEqual(data["total"], 0)

    # ------------------------------------------------------------------
    # The clicked product is a number anybody can type
    # ------------------------------------------------------------------
    def test_an_unpublished_product_says_nothing_about_itself(self):
        """Not its name, price, image, url, nor what it is filed under.

        ``hidden_category`` is worn by this product alone, so its name or id
        anywhere in the answer could only have come from the product.
        """
        response = self._post(self.unpublished.id)
        data = response.json()["result"]
        self.assertIsNone(data["current"])
        self.assertEqual(data["current_category_ids"], [])
        self.assertEqual(data["same_categories"], [])
        self.assertEqual(data["same_category_ids"], [])
        self.assertNotIn(self.hidden_category.id, {c["id"] for c in data["categories"]})
        self.assertNotIn("Compare Test Unpublished", response.text)
        self.assertNotIn("Compare Test Hidden Category", response.text)
        self.assertNotIn("product.template/%s/" % self.unpublished.id, response.text)
        self.assertNotIn(self.unpublished.website_url, response.text)
        # It is answered as a request with no product at all: no same
        # category, so no category filter either.
        bare = self._candidates(None)
        self.assertEqual(data["scopes"], bare["scopes"])
        self.assertEqual(data["scope"], bare["scope"])
        self.assertEqual(data["total"], bare["total"])

    def test_a_visible_product_still_gets_its_whole_payload(self):
        data = self._candidates(self.published.id)
        self.assertEqual(data["current"]["id"], self.published.id)
        self.assertEqual(data["current"]["name"], "Compare Test Published")
        self.assertEqual(data["current_category_ids"], [self.category.id])

    def test_a_product_id_that_is_not_an_id_is_no_product(self):
        """A word, a list or a dict is not worth a 500 on a public route."""
        bare = self._candidates(None)
        for garbage in ("abc", "", [1], {"id": 1}, True, -5, 0, 1.5, 2**31, 2**40):
            payload = self._post(garbage).json()
            self.assertNotIn("error", payload, garbage)
            data = payload["result"]
            self.assertIsNone(data["current"], garbage)
            self.assertEqual(data["same_categories"], [], garbage)
            self.assertEqual(data["total"], bare["total"], garbage)
        # A string of digits is still an id, as it was before.
        data = self._candidates(str(self.published.id))
        self.assertEqual(data["current"]["id"], self.published.id)

    # ------------------------------------------------------------------
    # The four steps: same category ticked, the others one click away
    # ------------------------------------------------------------------
    def _names(self, data):
        return {product["name"] for product in data["products"]}

    def test_it_opens_on_the_clicked_products_own_category(self):
        """Somebody looking at a computer is not shown the restaurants.

        No category parameter at all is the modal's first request. Children
        of the category ride along: "Computers" includes "Laptops".
        """
        data = self._candidates(self.published.id)
        self.assertEqual(
            data["same_categories"],
            [{"id": self.category.id, "name": "Compare Test Category"}],
        )
        self.assertEqual(data["same_category_ids"], [self.category.id])
        self.assertEqual(data["selected_category_ids"], [])
        self.assertEqual(
            self._names(data),
            {"Compare Test Other", "Compare Test Child", "Compare Test Multi"},
        )
        self.assertEqual(data["total"], 3)

    def test_unticking_the_same_category_with_nothing_else_is_no_filter(self):
        data = self._candidates(
            self.published.id, same_category_ids=[], query="Compare Test"
        )
        self.assertEqual(data["same_category_ids"], [])
        self.assertEqual(
            self._names(data),
            {
                "Compare Test Other",
                "Compare Test Child",
                "Compare Test Elsewhere",
                "Compare Test Second",
                "Compare Test Multi",
            },
        )
        # ... and without the name, it is the whole scope again.
        unfiltered = self._candidates(self.published.id, same_category_ids=[])
        self.assertGreater(unfiltered["total"], CANDIDATE_LIMIT)

    def test_another_category_adds_to_the_same_one(self):
        """Scope AND (same OR others): picking widens within the scope."""
        data = self._candidates(
            self.published.id, category_ids=[self.other_category.id]
        )
        self.assertEqual(data["same_category_ids"], [self.category.id])
        self.assertEqual(data["selected_category_ids"], [self.other_category.id])
        self.assertEqual(
            self._names(data),
            {
                "Compare Test Other",
                "Compare Test Child",
                "Compare Test Multi",
                "Compare Test Elsewhere",
            },
        )

    def test_another_category_alone_replaces_the_same_one(self):
        data = self._candidates(
            self.published.id,
            same_category_ids=[],
            category_ids=[self.other_category.id],
        )
        self.assertEqual(self._names(data), {"Compare Test Elsewhere"})

    def test_the_same_category_is_not_repeated_among_the_others(self):
        data = self._candidates(self.published.id)
        others = {c["id"] for c in data["categories"]}
        self.assertNotIn(self.category.id, others)
        self.assertIn(self.other_category.id, others)
        # Picking something does not make the rest of the chips go away.
        picked = self._candidates(
            self.published.id, category_ids=[self.other_category.id]
        )
        self.assertEqual({c["id"] for c in picked["categories"]}, others)

    def test_a_product_in_several_categories_shows_them_all_ticked(self):
        data = self._candidates(self.multi.id)
        expected = {self.category.id, self.second_category.id}
        self.assertEqual({c["id"] for c in data["same_categories"]}, expected)
        self.assertEqual(set(data["same_category_ids"]), expected)
        self.assertFalse(expected & {c["id"] for c in data["categories"]})
        self.assertEqual(
            self._names(data),
            {
                "Compare Test Published",
                "Compare Test Other",
                "Compare Test Child",
                "Compare Test Second",
            },
        )
        # Each of them unticks on its own.
        only_second = self._candidates(
            self.multi.id, same_category_ids=[self.second_category.id]
        )
        self.assertEqual(only_second["same_category_ids"], [self.second_category.id])
        self.assertEqual(self._names(only_second), {"Compare Test Second"})

    def test_a_product_with_no_category_has_no_same_category_step(self):
        data = self._candidates(self.needle.id)
        self.assertEqual(data["same_categories"], [])
        self.assertEqual(data["same_category_ids"], [])
        self.assertEqual(data["current_category_ids"], [])
        # No category, no filter: what the modal did before it had steps.
        self.assertGreater(data["total"], CANDIDATE_LIMIT)
        self.assertIn(self.category.id, {c["id"] for c in data["categories"]})

    def test_the_total_and_the_cap_are_those_of_the_ticked_category(self):
        """ "Showing 120 of N" has to be about the list on screen.

        The fillers share a category that holds more than the cap. Clicking
        one of them must count and truncate THAT category, not the scope.
        """
        clicked = self.fillers[0]
        data = self._candidates(clicked.id)
        self.assertEqual(data["same_category_ids"], [self.filler_category.id])
        self.assertEqual(data["total"], len(self.fillers) - 1)
        self.assertGreater(data["total"], CANDIDATE_LIMIT)
        self.assertEqual(len(data["products"]), CANDIDATE_LIMIT)
        for product in data["products"]:
            self.assertIn(self.filler_category.id, product["category_ids"])
        whole_scope = self._candidates(clicked.id, same_category_ids=[])
        self.assertGreater(whole_scope["total"], data["total"])

    def test_only_the_first_ids_of_a_long_list_are_read(self):
        padding = [2**31 - 1] * MAX_CLIENT_IDS
        ignored = self._candidates(
            self.published.id,
            same_category_ids=[],
            category_ids=padding + [self.other_category.id],
            query="Compare Test",
        )
        self.assertEqual(ignored["selected_category_ids"], [])
        read = self._candidates(
            self.published.id,
            same_category_ids=[],
            category_ids=padding[:-1] + [self.other_category.id],
            query="Compare Test",
        )
        self.assertEqual(read["selected_category_ids"], [self.other_category.id])
        self.assertEqual(self._names(read), {"Compare Test Elsewhere"})
        # The same cap guards the same-category list.
        unticked = self._candidates(
            self.published.id, same_category_ids=padding + [self.category.id]
        )
        self.assertEqual(unticked["same_category_ids"], [])

    def test_the_same_category_comes_from_the_product_not_from_the_client(self):
        """The client may untick; it may not name a category of its own."""
        data = self._candidates(
            self.published.id,
            same_category_ids=[self.other_category.id, self.hidden_category.id],
            query="Compare Test",
        )
        self.assertEqual(data["same_category_ids"], [])
        self.assertEqual(
            data["same_categories"],
            [{"id": self.category.id, "name": "Compare Test Category"}],
        )
        self.assertNotIn("Compare Test Unpublished", self._names(data))

    def test_garbage_category_ids_are_ignored(self):
        garbage = ["7", None, True, -3, 0, 1.5, [self.other_category.id], {"id": 1}]
        for category_ids in (garbage, "1 OR 1=1", {"a": 1}, 42):
            data = self._candidates(
                self.published.id,
                same_category_ids=[],
                category_ids=category_ids,
                query="Compare Test",
            )
            self.assertEqual(data["selected_category_ids"], [])
            self.assertNotIn("Compare Test Unpublished", self._names(data))
            self.assertEqual(len(data["products"]), 5)
        # Not a list at all is not "everything unticked": it is the default.
        data = self._candidates(self.published.id, same_category_ids="garbage")
        self.assertEqual(data["same_category_ids"], [self.category.id])

    def test_a_forged_category_never_reaches_outside_the_shop_domain(self):
        """A category that is no chip here is no filter here.

        ``hidden_category`` holds one product, unpublished. Naming it -- on
        its own, next to a real one, as "same" -- must never bring that
        product in, and whatever does come back is inside the answering
        website's own ``sale_product_domain()``.
        """
        portal = self.website._comparison_portal_website()
        allowed = set(
            self.env["product.template"]
            .with_context(website_id=portal.id)
            .search(Domain(portal.sale_product_domain()))
            .ids
        )
        forged = [
            {"category_ids": [self.hidden_category.id]},
            {"category_ids": [self.hidden_category.id], "same_category_ids": []},
            {
                "category_ids": [self.hidden_category.id, self.other_category.id],
                "same_category_ids": [self.hidden_category.id],
            },
            {"category_ids": [2**40], "same_category_ids": [2**40]},
        ]
        for params in forged:
            data = self._candidates(self.published.id, scope="all", **params)
            self.assertEqual(data["scope"], "all")
            self.assertNotIn(self.hidden_category.id, data["selected_category_ids"])
            self.assertNotIn(self.hidden_category.id, data["same_category_ids"])
            ids = {product["id"] for product in data["products"]}
            self.assertNotIn(self.unpublished.id, ids)
            self.assertLessEqual(ids, allowed)


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
        # fixture sites for no assertion. The carrier patch only applies when
        # website_sale_collect is actually installed (it is absent on the
        # clean CI database, and patching a missing attribute aborts the
        # class in setUpClass).
        carrier_cls = type(cls.env["delivery.carrier"])
        if hasattr(carrier_cls, "_check_warehouses_have_same_company"):
            cls.startClassPatcher(
                patch.object(
                    carrier_cls,
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

    def test_a_product_this_site_does_not_list_says_nothing_about_itself(self):
        """Published, but somebody else's: not on this website, not here.

        The portal only lists what carries the portal company. A product of
        a merchant that was never linked to it has a page on that merchant's
        own site and nowhere else, and asking the portal about it by id must
        answer exactly as an unpublished one does.
        """
        category = self.env["product.public.category"].create(
            {"name": "Zone HTTP Foreign Category"}
        )
        # `wsm_skip_marketplace_link`: creating a product normally links the
        # portal company to it, which is precisely what makes it listable.
        foreign = (
            self.env["product.template"]
            .with_context(wsm_skip_marketplace_link=True)
            .create(
                {
                    "name": "Zone HTTP Foreign",
                    "is_published": True,
                    "list_price": 13.0,
                    "company_ids": [(6, 0, self.elsewhere_company.ids)],
                    "public_categ_ids": [(6, 0, category.ids)],
                }
            )
        )
        self.assertNotIn(self.portal.company_id, foreign.company_ids)
        response = self.opener.post(
            self.base_url() + "/shop/compare/candidates",
            json={
                "params": {"product_template_id": foreign.id},
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
            },
        )
        data = response.json()["result"]
        self.assertIsNone(data["current"])
        self.assertEqual(data["current_category_ids"], [])
        self.assertEqual(data["same_categories"], [])
        self.assertNotIn("Zone HTTP Foreign", response.text)
        self.assertNotIn("product.template/%s/" % foreign.id, response.text)
        # No owner to name either: the scopes are those of a bare request.
        self.assertNotIn("shop", {scope["key"] for scope in data["scopes"]})
        # The one next to it, which the portal does list, is untouched.
        listed = self._candidates(self.clicked.id)
        self.assertEqual(listed["current"]["name"], "Zone HTTP Clicked")

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
            for p in self._candidates(self.clicked.id, scope="zone", query="Zone HTTP")[
                "products"
            ]
        ]
        self.assertIn("Zone HTTP Same Zone", names)
        self.assertNotIn("Zone HTTP Elsewhere", names)

    def test_outside_the_zone_excludes_the_zones_products(self):
        data = self._candidates(self.clicked.id, scope="other_zone", query="Zone HTTP")
        self.assertEqual(data["scope"], "other_zone")
        names = [p["name"] for p in data["products"]]
        self.assertNotIn("Zone HTTP Same Zone", names)
        self.assertIn("Zone HTTP Elsewhere", names)


@tagged("post_install", "-at_install")
class TestCompareCandidatesPlainSites(HttpCase):
    """Two plain merchant microsites, and what one may learn of the other.

    No marketplace anywhere: the clicked-product gate is then core's own
    ``sale_product_domain()`` -- ``company_id in (False, the site's company)``,
    which ``base_multi_company`` reads on ``company_ids`` -- searched as sudo.
    Sudo lifts the record rules, not the domain, and this pins that the
    domain alone keeps another merchant's published product out.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The usual two patches (see TestCompareCandidatesZones): creating a
        # company trips website_sale_collect where it is installed, and the
        # marketplace backfill has nothing to do here.
        carrier_cls = type(cls.env["delivery.carrier"])
        if hasattr(carrier_cls, "_check_warehouses_have_same_company"):
            cls.startClassPatcher(
                patch.object(
                    carrier_cls,
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
        # No marketplace at all, so nothing is aggregated anywhere and no
        # company gets linked to a product behind the fixtures' back.
        cls.env["website"].sudo().search([("is_marketplace", "=", True)]).write(
            {"is_marketplace": False}
        )
        # `no_microsite_auto`: auto_microsite_generator, where installed,
        # would give each new company a website of its own; the fixtures
        # build theirs. `wsm_skip_marketplace_link`: belt and braces on top
        # of "no marketplace" -- these products belong to ONE company.
        Company = cls.env["res.company"].with_context(no_microsite_auto=True)
        Product = cls.env["product.template"].with_context(
            wsm_skip_marketplace_link=True
        )
        cls.company_a = Company.create({"name": "Plain HTTP Shop A"})
        cls.company_b = Company.create({"name": "Plain HTTP Shop B"})
        # Site A answers the test server's own address, so the requests below
        # land on it (a website is picked by the request's host), not on
        # website 1. `test_the_requests_land_on_site_a` proves it.
        cls.site_a = cls.env["website"].create(
            {
                "name": "Plain HTTP Shop A",
                "company_id": cls.company_a.id,
                "domain": cls.base_url(),
            }
        )
        cls.site_b = cls.env["website"].create(
            {
                "name": "Plain HTTP Shop B",
                "company_id": cls.company_b.id,
                "domain": "https://plain-http-b.example",
            }
        )
        # Stored with no @api.depends: fixtures say so themselves.
        cls.company_a.website_id = cls.site_a
        cls.company_b.website_id = cls.site_b
        category = cls.env["product.public.category"].create(
            {"name": "Plain HTTP Category"}
        )

        def product(name, company):
            return Product.create(
                {
                    "name": name,
                    "is_published": True,
                    "sale_ok": True,
                    "list_price": 10.0,
                    "company_ids": [(6, 0, company.ids)],
                    "public_categ_ids": [(6, 0, category.ids)],
                }
            )

        cls.product_a = product("Plain HTTP Product A", cls.company_a)
        cls.sibling_a = product("Plain HTTP Sibling A", cls.company_a)
        cls.product_b = product("Plain HTTP Product B", cls.company_b)

    def _post(self, template_id, **params):
        return self.opener.post(
            self.base_url() + "/shop/compare/candidates",
            json={
                "params": {"product_template_id": template_id, **params},
                "jsonrpc": "2.0",
                "method": "call",
                "id": 1,
            },
        )

    def test_the_requests_land_on_site_a(self):
        """Only site A lists product A, so only there is it ``current``."""
        self.assertEqual(self.product_a.company_ids, self.company_a)
        self.assertEqual(self.product_b.company_ids, self.company_b)
        data = self._post(self.product_a.id).json()["result"]
        self.assertEqual(data["current"]["name"], "Plain HTTP Product A")
        self.assertEqual(data["scope"], "shop")
        self.assertEqual(
            [product["name"] for product in data["products"]],
            ["Plain HTTP Sibling A"],
        )

    def test_another_merchants_product_says_nothing_about_itself(self):
        """Published and saleable, but not this shop's: not here."""
        bare = self._post(None).json()["result"]
        response = self._post(self.product_b.id)
        data = response.json()["result"]
        self.assertEqual(data, bare)
        self.assertIsNone(data["current"])
        self.assertEqual(data["same_categories"], [])
        self.assertNotIn("Plain HTTP Product B", response.text)
        self.assertNotIn(self.product_b.website_url, response.text)
        self.assertNotIn("product.template/%s/" % self.product_b.id, response.text)
        self.assertNotIn("Plain HTTP Shop B", response.text)

    def test_another_merchants_product_is_never_a_candidate(self):
        for params in (
            {},
            {"same_category_ids": []},
            {"scope": "all"},
            {"scope": "shop", "query": "Plain HTTP"},
            {"same_category_ids": [], "query": "Plain HTTP Product B"},
        ):
            response = self._post(self.product_a.id, **params)
            ids = {p["id"] for p in response.json()["result"]["products"]}
            self.assertNotIn(self.product_b.id, ids, params)
            self.assertNotIn("Plain HTTP Product B", response.text, params)
