# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import random

from odoo import http
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_directory.models.website_directory_entry import ZONE_ALIASES

_logger = logging.getLogger(__name__)

PPG_OPTIONS = (12, 21, 24, 48)
DEFAULT_PPG = 21
VIEW_TYPES = ("grid", "list")
SHUFFLE_COOKIE = "directory_seed"
SHUFFLE_COOKIE_MAX_AGE = 86400  # 24h: everyone gets a fresh order every day


class WebsiteDirectory(http.Controller):
    """Public business directory (``/directorio``).

    Extension points for future bridge modules (silver economy,
    sustainability, zones...):

    * :meth:`_get_extra_filter_domain` to translate their own query string
      parameters into extra domain leaves.
    * The ``directory_sidebar_extra`` QWeb template to add filter cards to
      the sidebar.
    """

    # ------------------------------------------------------------------
    # Zone helpers
    # ------------------------------------------------------------------
    def _get_zone_from_website(self, website):
        """Infer the current zone from the website domain."""
        if not website or not website.domain:
            return "canarias"
        domain = website.domain.lower()
        if "guanarteme" in domain:
            return "guanarteme"
        if "tamaraceite" in domain:
            return "tamaraceite"
        if "frailes" in domain:
            return "lomolosfrailes"
        return "canarias"

    def _get_zone_options(self):
        """Zone selection (value, label) pairs for the sidebar filter."""
        field = request.env["website.directory.entry"]._fields["zone"]
        return field._description_selection(request.env)

    # ------------------------------------------------------------------
    # Shuffle (fair daily rotation of the businesses)
    # ------------------------------------------------------------------
    def _get_or_create_shuffle_seed(self):
        """Per-visitor seed, persisted in a cookie for a stable order."""
        if getattr(request, "shuffle_seed", None):
            return request.shuffle_seed
        seed_str = request.httprequest.cookies.get(SHUFFLE_COOKIE)
        if seed_str:
            try:
                request.shuffle_seed = int(seed_str)
                return request.shuffle_seed
            except (ValueError, TypeError):
                pass
        seed = random.randint(1, 1000000)
        request.shuffle_seed = seed
        request.shuffle_seed_is_new = True
        _logger.debug("Directory shuffle: new seed %s", seed)
        return seed

    def _apply_shuffle_order(self, record_ids):
        """Deterministic shuffle of a list of ids based on the seed."""
        if not record_ids:
            return record_ids
        record_ids = list(record_ids)
        random.Random(self._get_or_create_shuffle_seed()).shuffle(record_ids)
        return record_ids

    def _set_shuffle_cookie_if_needed(self, response):
        if getattr(request, "shuffle_seed_is_new", False):
            response.set_cookie(
                SHUFFLE_COOKIE,
                str(request.shuffle_seed),
                max_age=SHUFFLE_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
            )
        return response

    # ------------------------------------------------------------------
    # Domain building
    # ------------------------------------------------------------------
    def _get_extra_filter_domain(self, kw):
        """Extension hook: extra domain built from the query string.

        Bridge modules (e.g. ``website_directory_silver_economy``) override
        this method, read their own ``kw`` parameters and return additional
        domain leaves. The base module filters nothing here.
        """
        return []

    def _get_text_search_domain(self, search):
        """Free text search on the entry and its partner names.

        The l10n_es trade name (``comercial``) is included only when the
        field exists: it is not a dependency of this module.
        """
        search_fields = ["name", "company_id.partner_id.name"]
        if "comercial" in request.env["res.partner"]._fields:
            search_fields.append("company_id.partner_id.comercial")
        return Domain.OR([(f, "ilike", search)] for f in search_fields)

    def _get_search_domain(self, zone=None, category_id=None, search="", kw=None):
        """Domain of the published entries matching the current filters."""
        domain = Domain(
            [
                ("active", "=", True),
                ("is_published", "=", True),
                ("company_id.show_in_directory", "=", True),
                ("company_id.active", "=", True),
            ]
        )
        if zone and zone != "canarias":
            domain &= Domain("zone", "in", ZONE_ALIASES.get(zone, [zone]))
        if category_id:
            # res.company.category is _parent_store: child_of is one query.
            domain &= Domain("category_id", "child_of", int(category_id))
        if search:
            domain &= self._get_text_search_domain(search)
        extra_domain = self._get_extra_filter_domain(kw or {})
        if extra_domain:
            domain &= Domain(extra_domain)
        return domain

    # ------------------------------------------------------------------
    # Category helpers
    # ------------------------------------------------------------------
    def _get_category_tree(self):
        """Nested category data for the cascading filter (3 levels)."""

        def node(category, depth):
            children = []
            if depth < 3:
                children = [
                    node(child, depth + 1)
                    for child in category.child_ids.sorted("name")
                    if child.active
                ]
            return {"id": category.id, "name": category.name, "children": children}

        roots = (
            request.env["res.company.category"]
            .sudo()
            .search([("parent_id", "=", False)], order="name")
        )
        return [node(root, 1) for root in roots]

    def _get_selected_category_path(self, category_id):
        """Ids of the selected category lineage: [level1, level2, level3]."""
        path = [None, None, None]
        if not category_id:
            return path
        category = (
            request.env["res.company.category"].sudo().browse(int(category_id))
        ).exists()
        lineage = []
        while category:
            lineage.insert(0, category.id)
            category = category.parent_id
        for index, category_id_ in enumerate(lineage[:3]):
            path[index] = category_id_
        return path

    # ------------------------------------------------------------------
    # Rendering values
    # ------------------------------------------------------------------
    def _sanitize_int(self, value, default, minimum=1):
        try:
            return max(int(value), minimum)
        except (TypeError, ValueError):
            return default

    def _prepare_directory_values(self, page=1, zone=None, url="/directorio", **kw):
        """Single implementation of domain + shuffle + pager + categories."""
        page = self._sanitize_int(kw.get("page", page), 1)
        ppg = self._sanitize_int(kw.get("ppg"), DEFAULT_PPG)
        if ppg not in PPG_OPTIONS:
            ppg = DEFAULT_PPG
        view_type = kw.get("view") if kw.get("view") in VIEW_TYPES else "grid"
        search = (kw.get("search") or "").strip()
        category_id = kw.get("category")
        try:
            category_id = int(category_id) if category_id else None
        except (TypeError, ValueError):
            category_id = None

        entry_model = request.env["website.directory.entry"].sudo()
        domain = self._get_search_domain(
            zone=zone, category_id=category_id, search=search, kw=kw
        )
        entries_count = entry_model.search_count(domain)
        # Shuffle all matching ids with the visitor seed, then paginate.
        shuffled_ids = self._apply_shuffle_order(
            entry_model.search(domain, order="id").ids
        )
        offset = (page - 1) * ppg
        entries = entry_model.browse(shuffled_ids[offset : offset + ppg])

        url_args = {"search": search, "category": category_id or None}
        url_args.update(self._get_extra_pager_args(kw))
        pager = request.website.pager(
            url=url, total=entries_count, page=page, step=ppg, url_args=url_args
        )
        category_tree = self._get_category_tree()
        selected_path = self._get_selected_category_path(category_id)
        return {
            "entries": entries,
            "entries_count": entries_count,
            "search": search,
            "pager": pager,
            "page": page,
            "ppg": ppg,
            "view_type": view_type,
            "base_url": url,
            "category_tree": category_tree,
            "categories_json": json.dumps(
                {
                    "categories": category_tree,
                    "selected": selected_path,
                }
            ),
            "selected_category": category_id,
            "selected_category_path": selected_path,
            "zone_options": self._get_zone_options(),
        }

    def _get_extra_pager_args(self, kw):
        """Extension hook: extra query string args kept across pages."""
        return {}

    def _render_directory(self, values):
        response = request.render("website_directory.directory_index", values)
        return self._set_shuffle_cookie_if_needed(response)

    # ------------------------------------------------------------------
    # Routes
    # ------------------------------------------------------------------
    @http.route(
        ["/directorio", "/directorio/page/<int:page>"],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def directory_index(self, page=1, **kw):
        """Main directory page, filtered by the zone of the website."""
        current_zone = self._get_zone_from_website(request.website)
        values = self._prepare_directory_values(
            page=page,
            zone=current_zone if current_zone != "canarias" else None,
            url="/directorio",
            **kw,
        )
        values["current_zone"] = current_zone
        return self._render_directory(values)

    @http.route(
        [
            "/directorio/zona/<string:zone>",
            "/directorio/zona/<string:zone>/page/<int:page>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def directory_by_zone(self, zone, page=1, **kw):
        """Directory filtered by an explicit zone."""
        values = self._prepare_directory_values(
            page=page, zone=zone, url=f"/directorio/zona/{zone}", **kw
        )
        values["current_zone"] = zone
        return self._render_directory(values)

    @http.route(
        [
            "/directorio/categoria/<int:category_id>",
            "/directorio/categoria/<int:category_id>/page/<int:page>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def directory_by_category(self, category_id, page=1, **kw):
        """Directory filtered by a category (descendants included)."""
        category = request.env["res.company.category"].sudo().browse(category_id)
        if not category.exists():
            return request.not_found()
        current_zone = self._get_zone_from_website(request.website)
        kw["category"] = category_id
        values = self._prepare_directory_values(
            page=page,
            zone=current_zone if current_zone != "canarias" else None,
            url=f"/directorio/categoria/{category_id}",
            **kw,
        )
        values["current_zone"] = current_zone
        values["filter_category"] = category
        return self._render_directory(values)

    @http.route(
        "/directorio/ajax/search",
        type="http",
        auth="public",
        website=True,
        methods=["GET"],
        sitemap=False,
    )
    def directory_ajax_search(self, **kw):
        """Partial rendering (cards + pager) for the async filters."""
        current_zone = self._get_zone_from_website(request.website)
        values = self._prepare_directory_values(
            zone=current_zone if current_zone != "canarias" else None,
            url="/directorio",
            **kw,
        )
        values["current_zone"] = current_zone
        response = request.render("website_directory.directory_search_results", values)
        return self._set_shuffle_cookie_if_needed(response)

    @http.route(
        "/directorio/img/<int:entry_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def directory_image(self, entry_id, **kw):
        """Public image of an entry: own image, else the company logo.

        Streamed through ``ir.binary`` so the real mimetype, ETag and cache
        headers are handled by the standard Odoo machinery.
        """
        entry = request.env["website.directory.entry"].sudo().browse(entry_id)
        entry = entry.exists()
        if not entry or not entry.is_published:
            return request.not_found()
        if entry.image_1920:
            record, field_name = entry, "image_1920"
        else:
            record, field_name = entry.company_id, "logo"
        stream = request.env["ir.binary"]._get_image_stream_from(record, field_name)
        return stream.get_response()
