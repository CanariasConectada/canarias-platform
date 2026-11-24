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
        nothing on regular traffic. Aliases are plain 301 rewrites.
        """
        response = super()._serve_fallback()
        if response:
            return response
        path = (request.httprequest.path or "").rstrip("/").lower()
        website = getattr(request, "website", None)
        if not path or not website:
            return response
        campaign = (
            request.env["raffle.campaign"]
            .sudo()
            .search(
                [("website_id", "=", website.id), ("short_path", "=", path)],
                limit=1,
            )
        )
        if not campaign:
            return response
        from ..controllers.main import RaffleController

        response = RaffleController()._render_landing(campaign)
        response.flatten()
        return response
