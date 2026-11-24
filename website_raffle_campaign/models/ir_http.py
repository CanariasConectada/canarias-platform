# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.http import request


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    @classmethod
    def _serve_fallback(cls):
        """Serve a campaign at its short path (``/ticketaso``).

        The stock ``website.rewrite`` 308 only renames a ROUTE RULE, never a
        concrete URL, so it cannot map ``/ticketaso`` onto the parametrised
        ``/sorteo/<slug>``. The fallback runs only for paths nothing else
        claimed (no controller, no page, no redirect), so the lookup costs
        nothing on regular traffic. Aliases are also mirrored as plain 301 rewrites
        (visible in the website settings).
        """
        cls._frontend_pre_dispatch()
        # Sets request.website / request.lang and strips the language prefix;
        # the parent runs it again, which is harmless.
        cls._frontend_pre_dispatch()
        website = getattr(request, "website", None)
        path = (request.httprequest.path or "").rstrip("/").lower()
        campaigns = request.env["raffle.campaign"].sudo()
        # Aliases first, ours: the stock 301 rewrite drops the language prefix
        # (/fr/ticketazo -> /ticketaso), this keeps it.
        if path and website:
            for campaign in campaigns.search(
                [
                    ("website_id", "=", website.id),
                    ("alias_paths", "ilike", path),
                    ("short_path", "!=", False),
                ]
            ):
                if path in campaign._alias_list():
                    target = campaign.short_path
                    # Built by hand: _url_localized leaves unrouted paths bare.
                    if request.lang != cls._get_default_lang():
                        target = f"/{request.lang.url_code}{target}"
                    return request.redirect(target, code=301)
        response = super()._serve_fallback()
        if response:
            return response
        if not path or not website:
            return response
        campaign = campaigns.search(
            [("website_id", "=", website.id), ("short_path", "=", path)], limit=1
        )
        if not campaign:
            return response
        from ..controllers.main import RaffleController

        response = RaffleController()._render_landing(campaign)
        response.flatten()
        return response
