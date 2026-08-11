# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import http
from odoo.fields import Domain
from odoo.http import request

_logger = logging.getLogger(__name__)


class WebsiteSaleCanarias(http.Controller):
    """The shop's AJAX filter endpoint.

    The legacy platform filtered the aggregated shop without a page reload:
    picking a category, typing a search or moving the price slider fetched
    ``/shop/ajax/products`` and swapped the grid in place. This is that
    endpoint rebuilt on the reform's foundations — the product set comes from
    ``website._wsc_shop_domain()`` (i.e. from website_sale_marketplace's
    ``sale_product_domain``), never from a hand-rolled query, so AJAX results
    and the server-rendered page can never disagree about what is for sale.
    """

    @http.route(
        "/shop/ajax/products",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
        methods=["GET"],
    )
    def shop_ajax_products(
        self, category=None, search="", min_price=0.0, max_price=0.0, **kwargs
    ):
        website = request.website
        try:
            domain = website._wsc_shop_domain()
            category_record = None
            if category:
                category_record = (
                    request.env["product.public.category"]
                    .sudo()
                    .browse(int(category))
                    .exists()
                )
                if category_record:
                    domain &= Domain("public_categ_ids", "in", category_record.ids)
            if search:
                domain &= Domain("name", "ilike", search)

            products = (
                request.env["product.template"]
                .sudo()
                .search(domain, order="website_sequence asc, id desc")
            )

            # Price bounds are applied on the list price after the search,
            # exactly as the legacy endpoint did: the platform sells at list
            # price and the slider's promise is "hide what is out of range",
            # not "recompute every pricelist".
            min_value = float(min_price or 0)
            max_value = float(max_price or 0)
            if min_value > 0:
                products = products.filtered(lambda p: p.list_price >= min_value)
            if max_value > 0:
                products = products.filtered(lambda p: p.list_price <= max_value)

            html = request.env["ir.ui.view"]._render_template(
                "website_sale_canarias.shop_grid_ajax",
                {
                    "products": products,
                    "website": website,
                },
            )
            payload = {
                "html": html.decode("utf-8") if isinstance(html, bytes) else html,
                "count": len(products),
                "category_id": category_record.id if category_record else None,
                "category_name": category_record.name if category_record else None,
                "search": search,
                "price": {"min": min_value, "max": max_value}
                if (min_value or max_value)
                else {},
                "filters_active": bool(
                    category_record or search or min_value or max_value
                ),
            }
        except Exception:
            # The page has a full-reload fallback for any error; what must
            # never happen is a traceback page inside a JSON consumer.
            _logger.exception("shop_ajax_products failed on website %s", website.id)
            payload = {"error": "internal error"}
        return request.make_response(
            json.dumps(payload), headers=[("Content-Type", "application/json")]
        )
