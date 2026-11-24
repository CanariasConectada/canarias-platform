# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from werkzeug.exceptions import NotFound

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request
from odoo.tools import format_date

from ..models.raffle_campaign import MAX_UPLOAD_BYTES

REF_RE = re.compile(r"^[A-Z]{2,5}-\d{3,}$")
SESSION_KEY = "raffle_last_refs"


class RaffleController(http.Controller):
    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_campaign(self, slug, allow_draft=False):
        campaign = (
            request.env["raffle.campaign"]
            .sudo()
            .search(
                [("slug", "=", slug), ("website_id", "=", request.website.id)],
                limit=1,
            )
        )
        # Terms and thank-you pages of a draft stay hidden from the public
        # (the terms may still hold placeholders); the landing and the artwork
        # of a draft are public on purpose, see ``_render_landing``.
        if not campaign or (
            campaign.state == "draft" and not allow_draft and not self._is_admin()
        ):
            raise NotFound()
        return campaign

    @staticmethod
    def _is_admin():
        return request.env.user.has_group("base.group_system")

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

    @staticmethod
    def _long_date(day):
        return day and format_date(request.env, day, date_format="long")

    def _landing_values(self, campaign, values=None, error=None):
        today = campaign._raffle_today()
        return {
            "start_label": self._long_date(campaign.date_start),
            "end_label": self._long_date(campaign.date_end),
            "draw_label": self._long_date(campaign.draw_date),
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
        """The campaign page for the current phase.

        The public sees the form only while the campaign is open; before the
        start (a draft counts as "not started yet") and after the end they get
        a page of their own, inside the normal site layout. Admins always see
        the full page, with a notice when it is still a draft.
        """
        phase = campaign._public_phase()
        if phase != "open" and not self._is_admin():
            return self._render_status(campaign, phase)
        context = self._landing_values(campaign, values, error)
        context["preview_notice"] = self._is_admin() and campaign.state == "draft"
        return request.render("website_raffle_campaign.landing", context)

    def _render_status(self, campaign, phase):
        template = "coming_soon" if phase == "soon" else "ended"
        response = request.render(
            f"website_raffle_campaign.{template}",
            {
                "campaign": campaign,
                "main_object": campaign,
                "start_label": self._long_date(campaign.date_start),
                "draw_label": self._long_date(campaign.draw_date),
            },
        )
        # The page changes the day the campaign opens: never let a proxy or the
        # browser keep it.
        response.headers["Cache-Control"] = "no-cache"
        return response

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
        return self._render_landing(self._get_campaign(slug, allow_draft=True))

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
            {
                "campaign": campaign,
                "reference": ref,
                "draw_label": self._long_date(campaign.draw_date),
                "main_object": campaign,
            },
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
        campaign = self._get_campaign(slug, allow_draft=True)
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
