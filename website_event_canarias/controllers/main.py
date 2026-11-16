# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import http

from odoo.addons.website_event.controllers.main import WebsiteEventController


class WebsiteEventCanarias(WebsiteEventController):
    """Fall back to the events history when nothing upcoming is scheduled.

    The zones publish neighbourhood events in bursts — a fair, a market, a
    concert — and between bursts the default /event page ("upcoming only")
    is an empty room with the whole history one unlabelled dropdown away.
    When the visitor did not ask for a specific date range and there is
    nothing scheduled, show the past events instead, saying so; a page that
    answers "here is what this neighbourhood has held" beats one that
    answers "nothing".
    """

    @http.route()
    def events(self, page=1, slug_tags=None, **searches):
        response = super().events(page=page, slug_tags=slug_tags, **searches)
        if "date" in searches:
            # The visitor picked a range; empty or not, honour it.
            return response
        qcontext = getattr(response, "qcontext", None)
        if qcontext is None or qcontext.get("search_count"):
            # Redirect responses (the tag-slug canonicalisation) have no
            # qcontext; pages with results need no fallback.
            return response
        past = super().events(page=page, slug_tags=slug_tags, date="old", **searches)
        past_qcontext = getattr(past, "qcontext", None)
        if past_qcontext is None or not past_qcontext.get("search_count"):
            # No history either: the honest answer is the empty page.
            return response
        past_qcontext["wec_showing_past"] = True
        return past
