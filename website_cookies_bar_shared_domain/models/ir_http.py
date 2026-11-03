# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.http import request
from odoo.tools.json import scriptsafe as json_scriptsafe

from .website import CONSENT_COOKIE


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def get_frontend_session_info(self):
        """Hand the shared consent domain to the frontend.

        The value is deliberately NOT narrowed to the current host here:
        website pages are served from a response cache keyed by website, not
        by host (`website.page._get_cache_key`), so a host-dependent value
        would leak from one host to another through that cache. The browser
        applies the hostname guard itself, against `window.location`, which is
        also the only hostname the cookie will actually be judged against.
        The value is not a secret: it is the domain the visitor is browsing.
        """
        session_info = super().get_frontend_session_info()
        shared_domain = self.env["website"]._cookies_bar_shared_domain()
        if shared_domain:
            session_info["cookies_bar_shared_domain"] = shared_domain
        return session_info

    @classmethod
    def _is_allowed_cookie(cls, cookie_type):
        """Expire the legacy consent on the shared domain too.

        Core drops a pre-16.0 consent (`"true"` instead of a JSON object) with
        a host-only `Set-Cookie`, which cannot reach a cookie stored with
        `Domain=<shared>`. This module never writes that format on the shared
        domain, so this is purely defensive: without it, such a cookie would
        make core ask again on every request, forever.
        """
        result = super()._is_allowed_cookie(cookie_type)
        if cookie_type == "optional" and not result:
            cls._cookies_bar_expire_legacy_shared_consent()
        return result

    @classmethod
    def _cookies_bar_expire_legacy_shared_consent(cls):
        raw_consent = request.cookies.get(CONSENT_COOKIE)
        if not raw_consent:
            return
        try:
            is_legacy = not isinstance(json_scriptsafe.loads(raw_consent), dict)
        except ValueError:
            # Core has already raised on this value; nothing to add.
            return
        if not is_legacy:
            return
        shared_domain = request.env["website"]._cookies_bar_shared_domain_for_host(
            request.httprequest.host
        )
        if shared_domain:
            request.future_response.set_cookie(
                CONSENT_COOKIE, max_age=0, domain=shared_domain
            )
