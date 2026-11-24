# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from ..models.raffle_campaign import MAX_UPLOAD_BYTES

REF_RE = re.compile(r"^[A-Z]{2,5}-\d{3,}$")
SESSION_KEY = "raffle_last_refs"


class RaffleController(http.Controller):
    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_campaign(self, slug):
        campaign = (
            request.env["raffle.campaign"]
            .sudo()
            .search(
                [("slug", "=", slug), ("website_id", "=", request.website.id)],
                limit=1,
            )
        )
        # A draft is invisible to the public; admins may preview it.
        if not campaign or (
            campaign.state == "draft"
            and not request.env.user.has_group("base.group_system")
        ):
            raise NotFound()
        return campaign

    @staticmethod
    def _client_ip():
        """Best-effort address for the audit trail ONLY, never for decisions.

        Behind nginx and Traefik Odoo sees the proxy for nearly everyone, and
        both headers are client-controllable unless the proxy overwrites them.
        """
        headers = request.httprequest.headers
        return (headers.get("X-Real-IP") or request.httprequest.remote_addr or "")[:45]

    def _merchants(self, campaign):
        """Participating merchants as (id, label), by label."""
        merchants = campaign.participating_company_ids
        rows = [(m.id, (getattr(m, "comercial", False) or m.name)) for m in merchants]
        return sorted(rows, key=lambda row: row[1].casefold())

    def _landing_values(self, campaign, values=None, error=None):
        today = campaign._raffle_today()
        return {
            "campaign": campaign,
            "merchants": self._merchants(campaign),
            "is_open": campaign._is_open(),
            "not_started": today < campaign.date_start,
            "values": values or {},
            "error": error,
            "max_mb": MAX_UPLOAD_BYTES // (1024 * 1024),
            "today": today,
            "main_object": campaign,
        }

    def _render_landing(self, campaign, values=None, error=None):
        if campaign.state == "draft" and not request.env.user.has_group(
            "base.group_system"
        ):
            raise NotFound()
        return request.render(
            "website_raffle_campaign.landing",
            self._landing_values(campaign, values, error),
        )

    # ------------------------------------------------------------------
    # Public pages
    # ------------------------------------------------------------------
    @http.route(
        "/sorteo/<string:slug>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def landing(self, slug, **kwargs):
        return self._render_landing(self._get_campaign(slug))

    @http.route(
        "/sorteo/<string:slug>/bases",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def terms(self, slug, **kwargs):
        campaign = self._get_campaign(slug)
        return request.render(
            "website_raffle_campaign.terms",
            {"campaign": campaign, "main_object": campaign},
        )

    @http.route(
        "/sorteo/<string:slug>/gracias",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def thanks(self, slug, ref=None, **kwargs):
        campaign = self._get_campaign(slug)
        # Only echo a reference this very session just created.
        if not (
            ref and REF_RE.match(ref) and ref in request.session.get(SESSION_KEY, [])
        ):
            ref = None
        return request.render(
            "website_raffle_campaign.thanks",
            {"campaign": campaign, "reference": ref, "main_object": campaign},
        )

    @http.route(
        "/sorteo/<string:slug>/banner",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def banner(self, slug, **kwargs):
        """Serve the artwork. ``/web/image`` would refuse the public user
        (no read ACL on the model), and giving it one would expose entries."""
        campaign = self._get_campaign(slug)
        if not campaign.banner_image:
            raise NotFound()
        stream = request.env["ir.binary"]._get_image_stream_from(
            campaign, "banner_image"
        )
        return stream.get_response(max_age=3600)

    # ------------------------------------------------------------------
    # Submission
    # ------------------------------------------------------------------
    @http.route(
        "/sorteo/<string:slug>/submit",
        type="http",
        auth="public",
        website=True,
        methods=["POST"],
        sitemap=False,
        max_content_length=11 * 1024 * 1024,
    )
    def submit(self, slug, **post):
        campaign = self._get_campaign(slug)
        form = request.httprequest.form
        data = {
            "participant_name": form.get("participant_name"),
            "email": form.get("email"),
            "phone": form.get("phone"),
            "merchant_id": form.get("merchant_id"),
            "amount": form.get("amount"),
            "purchase_date": form.get("purchase_date"),
            "is_adult": form.get("is_adult"),
            "terms_accepted": form.get("terms_accepted"),
            "honeypot": form.get("website_url"),
        }
        kept = {k: v for k, v in data.items() if k not in ("honeypot",)}
        try:
            upload = None
            storage = request.httprequest.files.get("receipt")
            if storage and storage.filename:
                content = storage.stream.read(MAX_UPLOAD_BYTES + 1)
                upload = (storage.filename, content)
            entry = campaign._submit_entry(data, upload, self._client_ip())
        except UserError as exc:
            return self._render_landing(campaign, values=kept, error=str(exc))
        refs = request.session.get(SESSION_KEY, [])
        request.session[SESSION_KEY] = (refs + [entry.reference])[-5:]
        return request.redirect(
            f"/sorteo/{campaign.slug}/gracias?ref={entry.reference}"
        )

    # ------------------------------------------------------------------
    # Backend helper
    # ------------------------------------------------------------------
    @http.route("/raffle/qr/<int:campaign_id>", type="http", auth="user")
    def qr(self, campaign_id, **kwargs):
        if not request.env.user.has_group("base.group_system"):
            raise NotFound()
        campaign = request.env["raffle.campaign"].browse(campaign_id).exists()
        if not campaign:
            raise NotFound()
        return request.make_response(
            campaign._qr_png(),
            headers=[
                ("Content-Type", "image/png"),
                (
                    "Content-Disposition",
                    f'attachment; filename="qr-{campaign.slug}.png"',
                ),
            ],
        )
