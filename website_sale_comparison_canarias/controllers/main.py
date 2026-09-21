# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import http
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_sale_comparison_canarias.models.website import SCOPE_OTHER_ZONE

# What the picker will show at most. The comparison table itself caps at four
# products (``MAX_COMPARISON_PRODUCTS`` in core's utils); this is the size of
# the pool to choose FROM, kept bounded because the modal renders it all at
# once and the whole platform holds north of a thousand products.
CANDIDATE_LIMIT = 120


def _clean_ids(value):
    """Positive ints out of whatever the client sent, anything else dropped.

    The endpoint is public: ``category_ids`` may arrive as a string, a dict,
    a list of lists or a list holding ``True`` (which IS an int in Python).
    None of that is an error worth answering, it is simply not an id.
    """
    if not isinstance(value, (list, tuple)):
        return []
    return [
        item
        for item in value
        if isinstance(item, int) and not isinstance(item, bool) and item > 0
    ]


class WebsiteSaleComparisonCanarias(http.Controller):
    @http.route(
        "/shop/compare/candidates",
        type="jsonrpc",
        auth="public",
        website=True,
        readonly=True,
    )
    def compare_candidates(
        self,
        product_template_id=None,
        scope=None,
        zone=None,
        query=None,
        same_category_ids=None,
        category_ids=None,
        **kwargs,
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

        CATEGORIES NARROW TOO, AND THE SERVER OWNS BOTH LISTS. The modal has
        a "same category" step (the clicked product's own categories, ticked
        by default) and an "other categories" step (none ticked). The
        candidates are ``scope AND (ticked same categories OR picked other
        categories)``; with nothing ticked at all there is no category filter,
        which is what the modal did before it had steps.

        * The same-category set is read off the PRODUCT here. The client only
          says which of those it unticked (``same_category_ids``; absent means
          "all of them", the default on open), and whatever it sends is
          intersected with the product's real categories. Children ride along
          (``child_of``): a product filed under "Computers" compares against
          "Computers / Laptops" as well.
        * ``category_ids`` is intersected with the facets this very scope
          offers, so an id that is not a chip on screen is not a filter.
        * Both end up AND-ed onto the website-derived domain like the query,
          so a forged id can empty the list but never add a product to it.

        The filter runs here rather than in the browser because the pool is
        capped: filtering 120 alphabetical rows client-side for "laptops"
        would miss every laptop past the letter C.

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
                "same_categories": [],
                "same_category_ids": [],
                "products": [],
                "categories": [],
                "category_ids": [],
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
            excluded_company_ids = website._comparison_outside_zone_company_ids(current)
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

        same_categories = current.public_categ_ids
        if isinstance(same_category_ids, (list, tuple)):
            ticked = set(_clean_ids(same_category_ids))
            checked_same = same_categories.filtered(lambda c: c.id in ticked)
        else:
            # Absent (or not even a list): the default, everything ticked.
            checked_same = same_categories

        # Facets come from the scope BEFORE the category filter -- otherwise
        # picking one category would make every other chip disappear -- and
        # from the whole scope rather than the capped page.
        other_categories = self._other_category_facets(Product, domain, same_categories)
        picked_other = [
            category_id
            for category_id in dict.fromkeys(_clean_ids(category_ids))
            if category_id in other_categories
        ]

        category_domains = []
        if checked_same:
            category_domains.append(
                Domain("public_categ_ids", "child_of", checked_same.ids)
            )
        if picked_other:
            category_domains.append(Domain("public_categ_ids", "in", picked_other))
        if category_domains:
            # Narrowing only, like the query: AND-ed onto the website-derived
            # domain, never a domain of its own.
            domain &= Domain.OR(category_domains)

        total = Product.search_count(domain)
        products = Product.search(domain, limit=CANDIDATE_LIMIT, order="name")

        return {
            "current": self._serialise(current, target) if current else None,
            "current_category_ids": same_categories.ids,
            # Step 2 of the modal: the categories of the product they clicked,
            # which is what it opens narrowed to. Always listed, candidates or
            # not -- the category is what it is -- and `same_category_ids`
            # says which of them are still ticked.
            "same_categories": [
                {"id": category.id, "name": category.name}
                for category in same_categories
            ],
            "same_category_ids": checked_same.ids,
            "products": [self._serialise(product, target) for product in products],
            # Step 3: every OTHER category on offer in this scope. The ones of
            # step 2 are never repeated here.
            "categories": [
                {"id": key, "name": value}
                for key, value in sorted(
                    other_categories.items(), key=lambda kv: kv[1].casefold()
                )
            ],
            "category_ids": picked_other,
            "scopes": scopes,
            "scope": scope,
            "zone": zone or "",
            # So the client can say "showing 120 of N" when the pool is
            # bigger than what the modal renders.
            "total": total,
            "limit": CANDIDATE_LIMIT,
        }

    def _other_category_facets(self, Product, domain, same_categories):
        """``{id: name}`` of the categories on offer, minus ``same_categories``.

        Built from what is actually on offer, not from the whole category
        tree: a filter that returns nothing is worse than no filter. Grouped
        in SQL over the whole scope, because the page is capped and a facet
        list read off 120 alphabetical rows would hide most categories.
        """
        groups = Product._read_group(
            domain, groupby=["public_categ_ids"], aggregates=["__count"]
        )
        excluded = set(same_categories.ids)
        return {
            category.id: category.name
            for category, _count in groups
            if category and category.id not in excluded
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
