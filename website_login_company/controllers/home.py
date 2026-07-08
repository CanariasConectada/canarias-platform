# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Set the active company cookie according to the login website.

This addon replaces a legacy hand-patch of the Odoo core file
``addons/web/controllers/home.py`` (``Home._login_redirect``): when a user
logs in through a website whose company differs from their default one, the
``cids`` cookie is set to that single company so the user lands in the
website company context (the other allowed companies remain available in
the company switcher, just not selected).

Design constraints:

* It must be a strict no-op when there is no website in the request
  (XML-RPC, ``/web/become``, databases without a matching website, hosts
  that match no website domain). A previous core patch caused HTTP 500 on
  login in websiteless contexts.
* It must never break the login flow: any unexpected error is logged and
  swallowed, and the standard redirect is always returned.
* The cookie is only forced when the user actually has access to the
  website company; otherwise the standard Odoo behavior is kept (avoids
  the historic login bounce).
"""

import logging

from odoo.http import request

from odoo.addons.web.controllers.home import Home

_logger = logging.getLogger(__name__)

# Same lifetime the legacy core patch used (one year, in seconds).
CIDS_COOKIE_MAX_AGE = 86400 * 365


class WebsiteLoginCompanyHome(Home):
    def _login_redirect(self, uid, redirect=None):
        try:
            self._set_website_company_cookie(uid)
        except Exception:
            # Never break the login flow because of the company cookie.
            _logger.warning(
                "Could not set the website company cookie at login (uid=%s)",
                uid,
                exc_info=True,
            )
        return super()._login_redirect(uid, redirect=redirect)

    def _find_login_website(self):
        """Return the website the user is logging in from, if any.

        ``request.website`` is only bound on website-routed requests, so we
        fall back to matching the HTTP host against the website domains,
        exactly as the legacy core patch did for ``/web/login`` (which is
        not a ``website=True`` route).
        """
        website = getattr(request, "website", None)
        if website:
            return website
        httprequest = getattr(request, "httprequest", None)
        host = (getattr(httprequest, "host", "") or "").partition(":")[0]
        if not host:
            return None
        return (
            request.env["website"].sudo().search([("domain", "ilike", host)], limit=1)
        )

    def _set_website_company_cookie(self, uid):
        """Force the ``cids`` cookie to the login website company.

        No-op when there is no bound HTTP request, no matching website,
        the website has no company, or the user has no access to that
        company.
        """
        if not request:
            return
        website = self._find_login_website()
        if not website or not website.company_id:
            return
        company = website.company_id
        user = request.env["res.users"].sudo().browse(uid)
        if not user.exists() or company.id not in user.company_ids.ids:
            return
        # A single id: only the website company is selected, the rest of
        # the allowed companies stay available in the switcher dropdown.
        request.future_response.set_cookie(
            "cids", str(company.id), max_age=CIDS_COOKIE_MAX_AGE, path="/"
        )
