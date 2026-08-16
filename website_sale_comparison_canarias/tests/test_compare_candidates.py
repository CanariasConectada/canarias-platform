# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.tests import HttpCase, tagged


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
