# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.http import request


class Website(models.Model):
    _inherit = "website"

    def _raffle_banner_campaign(self):
        """The open campaign whose banner goes on this page, or nothing.

        Called from the layout of EVERY page of every website, so the cheap
        test (is this the homepage?) runs first and the search only on the
        homepage; the answer is memoised on the request because a layout can
        be rendered more than once (error pages, ``t-call`` from snippets).
        """
        self.ensure_one()
        empty = self.env["raffle.campaign"]
        if not request or not getattr(request, "httprequest", None):
            return empty
        cache = getattr(request, "_raffle_banner_cache", None)
        if cache is None:
            cache = {}
            request._raffle_banner_cache = cache
        if self.id not in cache:
            campaign = empty
            if self._raffle_is_homepage():
                campaign = self.env["raffle.campaign"]._open_campaign(self)
            cache[self.id] = campaign
        return cache[self.id]

    def _raffle_is_homepage(self):
        path = request.httprequest.path
        lang = getattr(request, "lang", None)
        if lang and lang.url_code and path.startswith("/" + lang.url_code):
            rest = path[len(lang.url_code) + 1 :]
            if not rest or rest.startswith("/"):
                path = rest or "/"
        home = (self.homepage_url or "/").rstrip("/") or "/"
        return (path.rstrip("/") or "/") == home
