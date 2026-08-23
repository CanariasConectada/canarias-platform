# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import http
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_sale_comparison_canarias.models.website import (
    SCOPE_OTHER_ZONE,
)

# What the picker will show at most. The comparison table itself caps at four
# products (``MAX_COMPARISON_PRODUCTS`` in core's utils); this is the size of
# the pool to choose FROM, kept bounded because the modal renders it all at
# once and the whole platform holds north of a thousand products.
CANDIDATE_LIMIT = 120


class WebsiteSaleComparisonCanarias(http.Controller):
    @http.route(
        "/shop/compare/candidates",
        type="jsonrpc",
        auth="public",
        website=True,
        readonly=True,
    )
    def compare_candidates(
        self, product_template_id=None, scope=None, zone=None, query=None, **kwargs
    ):
        """Products the visitor may compare the given one against.

        SCOPE IS A WEBSITE, NEVER A DOMAIN. Whichever of the four the visitor
        picks -- the whole platform, the product's neighbourhood, everything
        outside it, or the shop that sells this product -- the answer is
        resolved to a website and the candidates come from that website's own
        ``sale_product_domain()``.

        That is the entire safety argument for exposing this to anonymous
        visitors. "Toda Canarias Conectada" returns exactly what the portal
        shop shows; "Guanarteme" returns exactly what the Guanarteme shop
        shows. It cannot return an unpublished product and it cannot invent a
        scope the platform does not already serve as a page, because a domain
        written by hand here would be a second opinion about who may see what
        and the two would drift.

        An unknown or unavailable scope falls back to the default rather than
        being answered from the current site: a query string belongs to
        whoever is holding the address bar.

        ``query`` narrows by name and "outside my commercial zone" subtracts
        the product's own neighbourhood, and both are ONLY narrowing: every
        extra leaf is AND-ed on top of the website-derived
        ``sale_product_domain()``, so neither can widen what the resolved
        shop already shows.

        LANGUAGE IS SET BY HAND. ``http_routing``'s frontend language
        resolution (URL prefix > ``frontend_lang`` cookie > context > site
        default) only runs its redirect/context dance for ``type="http"``
        routes -- a ``type="jsonrpc"`` route never gets it, so
        ``request.env.context['lang']`` stayed at the DB's base language no
        matter what the visitor's cookie said. ``request.lang`` IS still
        computed correctly at routing time (it is read straight off the
        cookie, not off this dispatcher's context), so re-applying it here
        is enough for VIEW/record translations.

        This alone did NOT fix the scope labels, though (still English with
        a confirmed ``env.context['lang'] == 'es_ES'``): a SEPARATE bug in
        ``i18n/es.po`` was masking it -- see the comment there. Both were
        reported 2026-08-21/23 ("corrije el idioma").
        """
        website = request.website
        lang = request.lang.code if hasattr(request, "lang") else request.env.lang
        request.env = request.env(context=dict(request.env.context, lang=lang))
        website = website.with_env(request.env)
        Product = request.env["product.template"].sudo()

        current = Product.browse(int(product_template_id or 0)).exists()
        scopes = website._comparison_scopes(current)
        available = {entry["key"] for entry in scopes}
        if scope not in available:
            scope = website._comparison_default_scope(current)
        target = website._comparison_scope_website(scope, zone=zone, product=current)
        if not target:
            scope = website._comparison_default_scope(current)
            target = website._comparison_scope_website(scope, product=current)
        if not target:
            return {
                "current": None,
                "current_category_ids": [],
                "products": [],
                "categories": [],
                "scopes": scopes,
                "scope": scope,
                "zone": zone or "",
                "total": 0,
                "limit": CANDIDATE_LIMIT,
            }

        domain = Domain(target.sudo().sale_product_domain())
        if scope == SCOPE_OTHER_ZONE and not zone:
            # "Outside my commercial zone": the portal's catalogue minus the
            # product's own neighbourhood. Subtracting can only narrow what
            # the portal already shows, so the invariant holds.
            excluded_company_ids = website._comparison_outside_zone_company_ids(
                current
            )
            if excluded_company_ids:
                domain &= Domain("company_ids", "not in", excluded_company_ids)
        if current:
            domain &= Domain("id", "!=", current.id)
        if query:
            # Narrowing only: visibility still comes entirely from the
            # website-derived domain above.
            domain &= Domain("name", "ilike", query)

        # SEARCHED IN THE TARGET'S CONTEXT, not the visitor's. The domain alone
        # is not enough: `website_sale_marketplace` translates the `company_id`
        # and `website_published` leaves through `_search_company_id` /
        # `_search_website_published`, and both read `website_id` off the
        # CONTEXT to decide whether they are on a zone marketplace. Asking for
        # "solo en esta tienda" from the Guanarteme shop therefore came back
        # with 83 products instead of the shop's 56 -- the leaf said company 6
        # and the context widened it to the whole neighbourhood.
        Product = Product.with_context(website_id=target.id)
        total = Product.search_count(domain)
        products = Product.search(domain, limit=CANDIDATE_LIMIT, order="name")

        # Facets are built from what is actually on offer, not from the whole
        # category tree: a filter that returns nothing is worse than no filter.
        categories = {}
        for product in products:
            for category in product.public_categ_ids:
                categories[category.id] = category.name

        return {
            "current": self._serialise(current, target) if current else None,
            # The categories of the product they clicked, so the modal can open
            # already narrowed to "things like this one" -- which is what was
            # asked for -- while leaving every other category one click away.
            "current_category_ids": current.public_categ_ids.ids if current else [],
            "products": [self._serialise(product, target) for product in products],
            "categories": [
                {"id": key, "name": value}
                for key, value in sorted(categories.items(), key=lambda kv: kv[1])
            ],
            "scopes": scopes,
            "scope": scope,
            "zone": zone or "",
            # So the client can say "showing 120 of N" when the pool is
            # bigger than what the modal renders.
            "total": total,
            "limit": CANDIDATE_LIMIT,
        }

    def _serialise(self, product, website):
        """Only what the modal draws. Nothing else leaves the server.

        The price goes through ``_get_combination_info(only_template=True)``
        so the modal shows what the shop shows -- pricelist and tax display
        included. Asking for the template's own price instead would be one
        query cheaper and wrong on any site with a pricelist, and a comparator
        that disagrees with the product page about the price is worse than no
        comparator.

        ``website`` here is the site the scope resolved to, not the one the
        visitor is standing on: comparing against Guanarteme has to show
        Guanarteme's prices.
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
