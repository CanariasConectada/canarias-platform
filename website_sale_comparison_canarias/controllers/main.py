# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import http
from odoo.http import request

# What the picker will show at most. The comparison table itself caps at four
# products (``MAX_COMPARISON_PRODUCTS`` in core's utils); this is the size of
# the pool to choose FROM, kept bounded because the modal renders it all at
# once and a zone shop can hold north of a thousand products.
CANDIDATE_LIMIT = 120


class WebsiteSaleComparisonCanarias(http.Controller):
    @http.route(
        "/shop/compare/candidates",
        type="jsonrpc",
        auth="public",
        website=True,
        readonly=True,
    )
    def compare_candidates(self, product_template_id=None, **kwargs):
        """Products the visitor may compare the given one against.

        Scope is the website they are standing on, and it comes from
        ``website.sale_product_domain()`` -- the same domain ``/shop`` itself
        uses. That is the whole reason this endpoint is safe to expose to
        anonymous visitors: it cannot return an unpublished product, and it
        cannot return one belonging to another zone, because the shop's own
        rules already say so. Building a domain by hand here would be a second
        opinion about who may see what, and the two would drift.

        On the portal that means the whole catalogue; on a zone shop, that
        zone's products -- which works because a merchant's products carry
        their zone company (``zone_company_ownership``).
        """
        website = request.website
        Product = request.env["product.template"].sudo()

        current = Product.browse(int(product_template_id or 0)).exists()
        domain = website.sale_product_domain()
        if current:
            domain = [*domain, ("id", "!=", current.id)]

        products = Product.search(domain, limit=CANDIDATE_LIMIT, order="name")

        # Facets are built from what is actually on offer, not from the whole
        # category tree: a filter that returns nothing is worse than no filter.
        categories = {}
        for product in products:
            for category in product.public_categ_ids:
                categories[category.id] = category.name

        return {
            "current": self._serialise(current, website) if current else None,
            # The categories of the product they clicked, so the modal can open
            # already narrowed to "things like this one" -- which is what was
            # asked for -- while leaving every other category one click away.
            "current_category_ids": current.public_categ_ids.ids if current else [],
            "products": [self._serialise(product, website) for product in products],
            "categories": [
                {"id": key, "name": value}
                for key, value in sorted(categories.items(), key=lambda kv: kv[1])
            ],
        }

    def _serialise(self, product, website):
        """Only what the modal draws. Nothing else leaves the server.

        The price goes through ``_get_combination_info(only_template=True)``
        so the modal shows what the shop shows -- pricelist and tax display
        included. Asking for the template's own price instead would be one
        query cheaper and wrong on any site with a pricelist, and a comparator
        that disagrees with the product page about the price is worse than no
        comparator.
        """
        combination_info = product.with_context(
            website_id=website.id
        )._get_combination_info(only_template=True)
        return {
            "id": product.id,
            "variant_id": product.product_variant_id.id,
            "name": product.name,
            "price": combination_info.get("price"),
            "category_ids": product.public_categ_ids.ids,
            "image_url": website.image_url(product, "image_128"),
            "url": product.website_url,
        }
