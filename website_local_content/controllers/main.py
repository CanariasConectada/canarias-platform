# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import uuid
from urllib.parse import urlsplit

from odoo import http
from odoo.fields import Domain
from odoo.http import request

PPG = 12
SORT_OPTIONS = {
    "newest": "create_date desc, id desc",
    "oldest": "create_date asc, id asc",
    "likes": "like_count desc, id desc",
    "year_asc": "photo_year asc, id asc",
    "year_desc": "photo_year desc, id desc",
}
DEFAULT_SORT = "newest"
LIKE_COOKIE = "wlc_session"
LIKE_COOKIE_MAX_AGE = 365 * 24 * 60 * 60  # One year, as the legacy default.


class WebsiteLocalContent(http.Controller):
    """Public pages of every content type (``/explora/<type_slug>``).

    All routes are parameterized by the content type record, so a new
    vertical (a third legacy clone) is only a new
    ``website.local.content.type`` record: zero code.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_content_type(self, type_slug):
        """Content type of the URL, or 404 when unknown or not available."""
        content_type = (
            request.env["website.local.content.type"]
            .sudo()
            .search([("url_slug", "=", type_slug)], limit=1)
        )
        if not content_type or not content_type._is_available_on_website(
            request.website
        ):
            raise request.not_found()
        return content_type

    def _get_base_domain(self, content_type):
        """Published items of the type, visible on the current website.

        Items without websites are visible everywhere; items scoped to
        other websites are excluded (per-zone scoping, as in the legacy
        modules where each vertical belonged to a single microsite).
        """
        item_model = request.env["website.local.content.item"]
        return Domain(
            [
                ("type_id", "=", content_type.id),
                ("state", "=", "approved"),
                ("is_published", "=", True),
            ]
        ) & Domain(item_model._get_website_visibility_domain(request.website))

    def _get_search_domain(
        self, content_type, category_id, subcategory_id, search, decade
    ):
        domain = self._get_base_domain(content_type)
        if category_id:
            domain &= Domain("category_id", "=", category_id)
        if subcategory_id:
            domain &= Domain("subcategory_id", "=", subcategory_id)
        if search:
            domain &= Domain("name", "ilike", search) | Domain(
                "description", "ilike", search
            )
        if decade and content_type.use_photo_year:
            domain &= Domain("decade", "=", decade)
        return domain

    def _get_category_data(self, content_type):
        """Sidebar categories of the type with their published item counts."""
        item_model = request.env["website.local.content.item"].sudo()
        counts = dict(
            item_model._read_group(
                self._get_base_domain(content_type),
                ["category_id"],
                ["__count"],
            )
        )
        categories = (
            request.env["website.local.content.category"]
            .sudo()
            .search([("type_id", "=", content_type.id)])
        )
        return [
            {
                "id": category.id,
                "name": category.name,
                "count": counts.get(category, 0),
                "subcategories": [
                    {"id": sub.id, "name": sub.name} for sub in category.subcategory_ids
                ],
            }
            for category in categories
        ]

    def _get_decades(self, content_type):
        """Decades that actually have published items, newest first."""
        if not content_type.use_photo_year:
            return []
        item_model = request.env["website.local.content.item"].sudo()
        groups = item_model._read_group(
            self._get_base_domain(content_type) & Domain("decade", ">", 0),
            ["decade"],
            ["__count"],
        )
        return sorted((decade for decade, _count in groups), reverse=True)

    def _sanitize_int(self, value):
        try:
            return int(value) or None
        except (TypeError, ValueError):
            return None

    def _get_visitor_session_key(self):
        return request.httprequest.cookies.get(LIKE_COOKIE)

    def _is_safe_local_path(self, url):
        """Whether ``url`` is a same-site absolute path, safe to redirect to.

        Rejects absolute URLs (``http://evil``), protocol-relative URLs
        (``//evil``) and the backslash variant browsers normalize to the
        latter (``/\\evil`` -> ``//evil``), closing the open-redirect hole
        independently of Odoo's own ``request.redirect(local=True)`` guard.
        """
        if not url or not isinstance(url, str):
            return False
        # Browsers treat backslashes as forward slashes; normalize before
        # parsing so ``/\evil.com`` cannot masquerade as a local path.
        normalized = url.replace("\\", "/")
        parsed = urlsplit(normalized)
        if parsed.scheme or parsed.netloc:
            return False
        return normalized.startswith("/") and not normalized.startswith("//")

    # ------------------------------------------------------------------
    # Index and category browsing
    # ------------------------------------------------------------------
    @http.route(
        [
            "/explora/<string:type_slug>",
            "/explora/<string:type_slug>/page/<int:page>",
            "/explora/<string:type_slug>/categoria/<int:category_id>",
            "/explora/<string:type_slug>/categoria/<int:category_id>/page/<int:page>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def content_index(self, type_slug, page=1, category_id=None, **kw):
        """Index of a content type: hero, filters sidebar, grid and pager."""
        content_type = self._get_content_type(type_slug)
        category_id = category_id or self._sanitize_int(kw.get("category"))
        subcategory_id = self._sanitize_int(kw.get("subcategory"))
        decade = self._sanitize_int(kw.get("decade"))
        search = (kw.get("search") or "").strip()
        sort = kw.get("sort") if kw.get("sort") in SORT_OPTIONS else DEFAULT_SORT

        item_model = request.env["website.local.content.item"].sudo()
        domain = self._get_search_domain(
            content_type, category_id, subcategory_id, search, decade
        )
        items_count = item_model.search_count(domain)
        base_url = f"/explora/{content_type.url_slug}"
        if category_id:
            base_url += f"/categoria/{category_id}"
        pager = request.website.pager(
            url=base_url,
            total=items_count,
            page=page,
            step=PPG,
            url_args={
                "search": search or None,
                "subcategory": subcategory_id,
                "decade": decade,
                "sort": sort if sort != DEFAULT_SORT else None,
            },
        )
        items = item_model.search(
            domain, order=SORT_OPTIONS[sort], limit=PPG, offset=pager["offset"]
        )
        session_key = self._get_visitor_session_key()
        liked_item_ids = []
        if session_key:
            liked_item_ids = (
                request.env["website.local.content.like"]
                .sudo()
                .search([("session_key", "=", session_key)])
                .mapped("item_id")
                .ids
            )
        return request.render(
            "website_local_content.content_index",
            {
                # Page <title>: "<type name> | <website name>" (the website
                # name is appended by website.layout).
                "additional_title": content_type.name,
                "content_type": content_type,
                "items": items,
                "items_count": items_count,
                "pager": pager,
                "search": search,
                "sort": sort,
                "category_id": category_id,
                "subcategory_id": subcategory_id,
                "decade": decade,
                "categories": self._get_category_data(content_type),
                "decades": self._get_decades(content_type),
                "liked_item_ids": liked_item_ids,
                "base_url": base_url,
                "index_url": f"/explora/{content_type.url_slug}",
            },
        )

    # ------------------------------------------------------------------
    # Detail page
    # ------------------------------------------------------------------
    @http.route(
        "/explora/<string:type_slug>/<string:item_slug>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def content_detail(self, type_slug, item_slug, **kw):
        content_type = self._get_content_type(type_slug)
        item = (
            request.env["website.local.content.item"]
            .sudo()
            .search(
                self._get_base_domain(content_type) & Domain("slug", "=", item_slug),
                limit=1,
            )
        )
        if not item:
            raise request.not_found()
        session_key = self._get_visitor_session_key()
        return request.render(
            "website_local_content.content_detail",
            {
                # Page <title>: "<item> - <type> | <website name>".
                "additional_title": f"{item.name} - {content_type.name}",
                "content_type": content_type,
                "item": item,
                "already_liked": item.has_session_liked(session_key),
                "index_url": f"/explora/{content_type.url_slug}",
            },
        )

    # ------------------------------------------------------------------
    # Images (streamed via ir.binary: mimetype, ETag and cache handled
    # by the standard Odoo machinery, no public attachments needed)
    # ------------------------------------------------------------------
    @http.route(
        [
            "/explora/<string:type_slug>/img/<int:item_id>",
            "/explora/<string:type_slug>/img/<int:item_id>/<int:image_id>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def content_image(self, type_slug, item_id, image_id=None, **kw):
        """Main image of an item, or one of its gallery images."""
        self._get_content_type(type_slug)
        item = request.env["website.local.content.item"].sudo().browse(item_id)
        item = item.exists()
        if (
            not item
            or item.state != "approved"
            or not item.is_published
            or not item._is_visible_on_website(request.website)
        ):
            return request.not_found()
        record = item
        if image_id:
            gallery_image = item.image_ids.filtered(lambda i: i.id == image_id)
            if not gallery_image:
                return request.not_found()
            record = gallery_image
        stream = request.env["ir.binary"]._get_image_stream_from(record, "image_1920")
        return stream.get_response()

    # ------------------------------------------------------------------
    # Likes (server-rendered form POST: no frontend JS at all)
    # ------------------------------------------------------------------
    @http.route(
        "/explora/<string:type_slug>/like/<int:item_id>",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
    )
    def content_like(self, type_slug, item_id, **kw):
        """Register one anonymous like per visitor session and redirect back."""
        self._get_content_type(type_slug)
        item = request.env["website.local.content.item"].sudo().browse(item_id)
        item = item.exists()
        if (
            not item
            or item.state != "approved"
            or not item.is_published
            or not item._is_visible_on_website(request.website)
        ):
            return request.not_found()
        session_key = self._get_visitor_session_key()
        is_new_session = not session_key
        if is_new_session:
            session_key = str(uuid.uuid4())
        if not item.has_session_liked(session_key):
            request.env["website.local.content.like"].sudo().create(
                {
                    "item_id": item.id,
                    "session_key": session_key,
                    "ip_address": request.httprequest.remote_addr,
                }
            )
        # Only redirect within the current site; anything else (external,
        # protocol-relative or the backslash bypass) falls back to the item.
        redirect_url = kw.get("redirect")
        if not self._is_safe_local_path(redirect_url):
            redirect_url = item.website_url
        response = request.redirect(redirect_url)
        response.set_cookie(
            LIKE_COOKIE,
            session_key,
            max_age=LIKE_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
        )
        return response

    # ------------------------------------------------------------------
    # Legacy URLs: the verticals lived under /memoria-viva and
    # /lugares-de-interes. Permanent redirects keep old links working.
    # ------------------------------------------------------------------
    @http.route(
        [
            "/memoria-viva",
            "/memoria-viva/<path:rest>",
            "/lugares-de-interes",
            "/lugares-de-interes/<path:rest>",
        ],
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def content_legacy_redirect(self, rest=None, **kw):
        """301 from the historical module URLs to /explora/<type_slug>."""
        path = request.httprequest.path
        for legacy_prefix in ("/memoria-viva", "/lugares-de-interes"):
            if path.startswith(legacy_prefix):
                path = path.replace(legacy_prefix, f"/explora{legacy_prefix}", 1)
                break
        query = request.httprequest.query_string.decode()
        return request.redirect(path + (f"?{query}" if query else ""), code=301)
