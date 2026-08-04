# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import random

from odoo import http
from odoo.exceptions import AccessError, UserError
from odoo.fields import Domain
from odoo.http import request

from odoo.addons.website_directory.models.website_directory_entry import (
    ZONE_ALIASES,
    ZONE_SELECTION,
)

_logger = logging.getLogger(__name__)

PPG_OPTIONS = (12, 21, 24, 48)
DEFAULT_PPG = 21
# "canarias" is the global zone: no neighbourhood filter, every business shows.
DEFAULT_ZONE = "canarias"
KNOWN_ZONES = frozenset(key for key, _label in ZONE_SELECTION)
# FALLBACK ONLY (see _get_zone_from_website): substring of the website domain
# mapped to a zone. Unchanged on purpose — every website that is not a zone
# marketplace has to keep resolving exactly as it does today.
DOMAIN_ZONE_HINTS = (
    ("guanarteme", "guanarteme"),
    ("tamaraceite", "tamaraceite"),
    ("frailes", "lomolosfrailes"),
)
VIEW_TYPES = ("grid", "list")
SHUFFLE_COOKIE = "directory_seed"
SHUFFLE_COOKIE_MAX_AGE = 86400  # 24h: everyone gets a fresh order every day


def _normalise_zone(raw):
    """Canonical zone key for a stored value, or ``None`` when unknown.

    Migrated rows still carry legacy spellings ("lomo_los_frailes", "lomo los
    frailes"), which is why ``ZONE_ALIASES`` exists in the first place.
    ``res_company_zone.res.company._normalise_zone`` applies the very same
    mapping to the company field; both read ``ZONE_ALIASES``/``ZONE_SELECTION``
    from this module, so the two cannot drift apart.

    Unknown values return ``None`` rather than the global zone, so the caller
    can tell "nothing usable here" from "explicitly global".
    """
    value = (raw or "").strip().lower()
    if not value:
        return None
    for canonical, aliases in ZONE_ALIASES.items():
        if value in aliases:
            return canonical
    return value if value in KNOWN_ZONES else None


class WebsiteDirectory(http.Controller):
    """Public business directory (``/comercio``).

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
    def _get_marketplace_zone(self, website):
        """Zone this website's marketplace is pinned to, or ``None``.

        ``website.marketplace_zone`` belongs to ``website_sale_marketplace``,
        which is checked for instead of depended on: the directory is useful
        without the aggregated shop, and the dependency would run the wrong
        way (the marketplace does not need the directory either).

        This is the *declared* zone of the website, set on the website itself.
        It is what the three neighbourhood portals already carry, and it is the
        whole point of this resolution: it survives a domain rename, a ``www.``
        variant or a staging URL, all of which used to make a neighbourhood
        portal silently list the entire platform.

        No ``sudo()`` here, deliberately. This runs in a PUBLIC controller, but
        ``request.website`` is already readable by the public user: core grants
        ``base.group_public`` read access on the ``website`` model
        (``website/security/ir.model.access.csv``) and no ``ir.rule`` narrows
        it for that group. Reading one stored field off the website record is
        the same unprivileged read the domain heuristic below has always done.
        The trap documented in
        ``website_sale_marketplace.website._zone_company_ids()`` is a different
        one: it walks into ``res.company``, where the public user only sees its
        own company. We never leave the website record.
        """
        if "marketplace_zone" not in website._fields:
            return None
        raw = website.marketplace_zone
        if not raw:
            # The global marketplace (the main portal) has no zone: it is meant
            # to list every business. Nothing anomalous, nothing to log.
            return None
        zone = _normalise_zone(raw)
        if not zone:
            # Only genuinely broken state reaches this: ``marketplace_zone``
            # takes its selection from ``res.company.commercial_zone``, which
            # takes it from ZONE_SELECTION, so the ORM cannot store an unknown
            # value — only a bad migration or a manual UPDATE can. Worth a
            # WARNING because the portal silently goes global; unreachable on
            # any normal request, so it cannot flood the log.
            _logger.warning(
                "Website %s (%s) has an unknown marketplace zone %r: it is not "
                "one of %s, so /comercio falls back and lists EVERY business.",
                website.id,
                website.domain or "",
                raw,
                sorted(KNOWN_ZONES),
            )
        return zone

    def _get_domain_zone(self, website):
        """Zone guessed from the website domain, or ``None``."""
        domain = (website.domain or "").lower()
        if not domain:
            return None
        for hint, zone in DOMAIN_ZONE_HINTS:
            if hint in domain:
                return zone
        return None

    def _get_zone_from_website(self, website):
        """Zone whose businesses this website's directory lists.

        Resolution order:

        1. ``website.marketplace_zone`` — the zone declared on the website
           itself. Authoritative: the three neighbourhood portals carry it and
           it keeps working through a domain rename.
        2. the domain substring heuristic — unchanged, so every website that
           declares no zone (the ~180 business microsites, among others) keeps
           resolving exactly as it always has.
        3. the global zone, i.e. no neighbourhood filter.

        The company zone is deliberately NOT consulted. Measured on the live
        database: the companies behind the three portals sit in ``canarias``
        (they are platform companies, not neighbourhood businesses), so it
        fixes nothing there, while the business microsites do carry a real
        zone — reading it would have narrowed 83% of the live sites from the
        whole platform down to their own street, a change nobody asked for.

        Nothing is logged on any path reached by a normal request: ``/comercio``
        is a high-traffic page and this deployment has no log rotation.
        """
        if not website:
            return DEFAULT_ZONE
        return (
            self._get_marketplace_zone(website)
            or self._get_domain_zone(website)
            or DEFAULT_ZONE
        )

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

        The query is split into words and every word must appear in one of the
        searched fields, instead of matching the whole string as a single
        ``ilike``. With the whole string, word order decided the result:
        "muebles siony" found the shop and "siony muebles" found nothing,
        because ``%siony muebles%`` never occurs in "MUEBLES SIONY".

        Accents are already handled by PostgreSQL — the database has the
        ``unaccent`` extension and Odoo runs with ``unaccent = true``, so
        "cafeteria" and "cafetería" match each other.

        The l10n_es trade name (``comercial``) is included only when the
        field exists: it is not a dependency of this module.
        """
        search_fields = ["name", "company_id.partner_id.name"]
        if "comercial" in request.env["res.partner"]._fields:
            search_fields.append("company_id.partner_id.comercial")
        words = search.split()
        if not words:
            return Domain.TRUE
        return Domain.AND(
            [
                Domain.OR([(field, "ilike", word)] for field in search_fields)
                for word in words
            ]
        )

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
        if zone and zone != DEFAULT_ZONE:
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
            return {
                "id": category.id,
                "name": category.name,
                "children": children,
                # A "view" category is a folder: it groups other categories
                # and ``set_own_directory_category`` refuses to assign it. The
                # merchant form must not offer as a choice something the model
                # rejects, so it renders those nodes as plain group labels.
                # The public filter is unaffected: it filters with ``child_of``
                # and a folder is a perfectly good filter there.
                "selectable": category.type == "normal",
            }

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

    def _prepare_directory_values(self, page=1, zone=None, url="/comercio", **kw):
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
        ["/comercio", "/comercio/page/<int:page>"],
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
            zone=current_zone if current_zone != DEFAULT_ZONE else None,
            url="/comercio",
            **kw,
        )
        values["current_zone"] = current_zone
        return self._render_directory(values)

    @http.route(
        [
            "/comercio/zona/<string:zone>",
            "/comercio/zona/<string:zone>/page/<int:page>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def directory_by_zone(self, zone, page=1, **kw):
        """Directory filtered by an explicit zone."""
        values = self._prepare_directory_values(
            page=page, zone=zone, url=f"/comercio/zona/{zone}", **kw
        )
        values["current_zone"] = zone
        return self._render_directory(values)

    @http.route(
        [
            "/comercio/categoria/<int:category_id>",
            "/comercio/categoria/<int:category_id>/page/<int:page>",
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
            zone=current_zone if current_zone != DEFAULT_ZONE else None,
            url=f"/comercio/categoria/{category_id}",
            **kw,
        )
        values["current_zone"] = current_zone
        values["filter_category"] = category
        return self._render_directory(values)

    @http.route(
        "/comercio/ajax/search",
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
            zone=current_zone if current_zone != DEFAULT_ZONE else None,
            url="/comercio",
            **kw,
        )
        values["current_zone"] = current_zone
        response = request.render("website_directory.directory_search_results", values)
        return self._set_shuffle_cookie_if_needed(response)

    @http.route(
        "/comercio/img/<int:entry_id>",
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
        # Enumerable ids: re-check the SAME visibility conditions as the
        # directory listing domain (see ``_get_search_domain``) so this public
        # route can never leak the logo of a hidden, archived or unpublished
        # business.
        if (
            not entry
            or not entry.is_published
            or not entry.active
            or not entry.company_id.show_in_directory
            or not entry.company_id.active
        ):
            return request.not_found()
        if entry.image_1920:
            record, field_name = entry, "image_1920"
        else:
            record, field_name = entry.company_id, "logo"
        stream = request.env["ir.binary"]._get_image_stream_from(record, field_name)
        return stream.get_response()

    # ------------------------------------------------------------------
    # Legacy URLs: the directory lived under /directorio until 19.0.7.0.0.
    # Permanent redirects keep old links (search engines, shared URLs,
    # printed QR codes) working after the rename to /comercio.
    # ------------------------------------------------------------------
    @http.route(
        [
            "/directorio",
            "/directorio/page/<int:page>",
            "/directorio/zona/<string:zone>",
            "/directorio/zona/<string:zone>/page/<int:page>",
            "/directorio/categoria/<int:category_id>",
            "/directorio/categoria/<int:category_id>/page/<int:page>",
            "/directorio/ajax/search",
            "/directorio/img/<int:entry_id>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def directory_legacy_redirect(self, **kw):
        """301 from the historical /directorio paths to /comercio."""
        path = request.httprequest.path.replace("/directorio", "/comercio", 1)
        query = request.httprequest.query_string.decode()
        return request.redirect(path + (f"?{query}" if query else ""), code=301)

    # ------------------------------------------------------------------
    # Merchant self-service
    # ------------------------------------------------------------------
    @http.route(
        "/mi-comercio",
        type="http",
        auth="user",
        website=True,
        sitemap=False,
    )
    def my_business(self, saved=None, error=None, **kw):
        """Where a merchant sets the category their shop is listed under.

        This page exists because a merchant could not do it anywhere: they are
        portal users, they have no backend, and writing ``category_id`` on
        ``res.company`` needs Administration rights. Measured on a real
        merchant account: reading the category worked, saving it raised
        ``AccessError``.

        That gap is why 49 businesses have no category at all and 40 sit under
        "Tienda de animales" — a bucket inherited from the old system, where
        the exact same 40 are. Whoever knows what a shop sells is the shop.
        """
        company = request.env["res.company"]._get_own_company_for_directory()
        return request.render(
            "website_directory.my_business",
            {
                "company": company,
                "categories": self._get_category_tree(),
                "selected_path": self._get_selected_category_path(
                    company.category_id.id if company else None
                ),
                "saved": saved,
                "error": error,
            },
        )

    @http.route(
        "/mi-comercio/categoria",
        type="http",
        auth="user",
        website=True,
        methods=["POST"],
        csrf=True,
        sitemap=False,
    )
    def my_business_set_category(self, category_id=None, **kw):
        """Save the category. The company comes from the session, not the form.

        The form never carries a company id, so there is nothing to tamper
        with: ``set_own_directory_category`` resolves the company from the
        logged-in user and writes that one or none.
        """
        try:
            request.env["res.company"].set_own_directory_category(category_id)
        except (AccessError, UserError) as exc:
            _logger.info(
                "Rejected category change by user %s: %s", request.env.uid, exc
            )
            return request.redirect("/mi-comercio?error=1")
        return request.redirect("/mi-comercio?saved=1")
