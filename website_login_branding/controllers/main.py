# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

import hashlib
import hmac as hmac_lib
import logging
import secrets
import time
from urllib.parse import urlsplit

from odoo import http
from odoo.http import request

try:  # Odoo's helper keys the HMAC with `database.secret` and adds a scope.
    from odoo.tools.misc import hmac as odoo_hmac
except ImportError:  # pragma: no cover - stripped-down build without the helper
    odoo_hmac = None

_logger = logging.getLogger(__name__)

# Signed reuse cookie: value is "<uid>.<hmac>". The HMAC is what stops a client
# from handing us an arbitrary uid and being logged in as a real user.
GUEST_COOKIE = "cc_guest"
GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
GUEST_HMAC_SCOPE = "website_login_branding.guest"

# Soft abuse cap. Repeat visitors reuse their signed cookie and never create a
# user, so this only throttles a flood of BRAND-NEW anonymous sessions (bots).
# It is a global rolling-window counter kept in ir.config_parameter: cheap,
# admin-tunable, and intentionally approximate (a small race around the counter
# may let a handful through -- acceptable for a soft cap, not a quota).
GUEST_WINDOW_SECONDS = 60 * 60  # 1 hour window
GUEST_WINDOW_MAX = 200  # new guests per window before creation is refused
GUEST_WINDOW_START_PARAM = "website_login_branding.guest_window_start"
GUEST_WINDOW_COUNT_PARAM = "website_login_branding.guest_window_count"


class GuestAccess(http.Controller):
    """Public entry point that logs a visitor in as an anonymous portal guest."""

    @http.route(
        "/guest/enter",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        sitemap=False,
    )
    def guest_enter(self, redirect=None, **kw):
        """Log the visitor in as a reusable anonymous guest, then redirect.

        Flow:

        1. Sanitize the ``redirect`` target to a same-site path (open-redirect
           guard). Anything else falls back to ``/``.
        2. If already logged in, do nothing but redirect -- never spawn or swap
           an account under an authenticated session.
        3. Reuse the guest identified by a VALID signed cookie; otherwise, if
           the soft cap allows, create a fresh one.
        4. Rotate a throwaway password and authenticate the session with it,
           keeping no plaintext around.
        5. Best-effort Discuss/push wiring, then set the signed reuse cookie.
        """
        target = redirect if self._is_safe_local_path(redirect) else "/"

        if request.session.uid:
            return request.redirect(target)

        user = self._resolve_cookie_guest()
        if not user:
            if not self._creation_allowed():
                _logger.warning(
                    "website_login_branding: guest creation throttled (from %s)",
                    request.httprequest.remote_addr,
                )
                # Degrade gracefully to anonymous browsing rather than 500.
                return request.redirect(target)
            user = request.env["res.users"].sudo()._create_platform_guest()

        # Fresh throwaway password on every entry; never stored or logged.
        password = secrets.token_urlsafe(24)
        user.sudo().write({"password": password})
        request.session.authenticate(
            request.env,
            {"login": user.login, "type": "password", "password": password},
        )

        # Discuss membership is a nicety; a failure must not undo the login.
        user.sudo()._join_community_channel()

        response = request.redirect(target)
        response.set_cookie(
            GUEST_COOKIE,
            self._sign_guest(user.id),
            max_age=GUEST_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=request.httprequest.is_secure,
        )
        return response

    # ------------------------------------------------------------------
    # Redirect safety
    # ------------------------------------------------------------------

    @staticmethod
    def _is_safe_local_path(url):
        """Whether ``url`` is a same-site absolute path, safe to redirect to.

        Rejects absolute URLs (``http://evil``), protocol-relative URLs
        (``//evil``) and the backslash variant browsers normalize to the latter
        (``/\\evil`` -> ``//evil``), closing the open-redirect hole.
        """
        if not url or not isinstance(url, str):
            return False
        normalized = url.replace("\\", "/")
        parsed = urlsplit(normalized)
        if parsed.scheme or parsed.netloc:
            return False
        return normalized.startswith("/") and not normalized.startswith("//")

    # ------------------------------------------------------------------
    # Signed reuse cookie
    # ------------------------------------------------------------------

    def _sign_guest(self, uid):
        """Return the signed cookie value ``"<uid>.<hmac>"`` for ``uid``."""
        return "%s.%s" % (uid, self._guest_hmac(uid))

    def _guest_hmac(self, uid):
        """HMAC-SHA256 over ``uid``, keyed by ``database.secret``.

        Prefers Odoo's ``tools.misc.hmac`` (same secret, plus a scope so the
        signature cannot be replayed in another context) and falls back to
        stdlib on a build that lacks the helper.
        """
        message = str(uid)
        if odoo_hmac is not None:
            return odoo_hmac(request.env(su=True), GUEST_HMAC_SCOPE, message)
        secret = (
            request.env["ir.config_parameter"].sudo().get_param("database.secret") or ""
        )
        return hmac_lib.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

    def _resolve_cookie_guest(self):
        """The guest user a VALID signed cookie points to, or ``None``.

        Never trusts the uid in the cookie without a matching HMAC, and even
        then only returns the user if it still exists, is active and is still
        flagged as a platform guest (a repurposed id must not grant a session).
        """
        cookie = request.httprequest.cookies.get(GUEST_COOKIE)
        if not cookie or "." not in cookie:
            return None
        uid_str, _sep, _mac = cookie.partition(".")
        if not uid_str.isdigit():
            return None
        # Constant-time comparison over the whole "<uid>.<hmac>" string.
        if not hmac_lib.compare_digest(cookie, self._sign_guest(int(uid_str))):
            return None
        user = request.env["res.users"].sudo().browse(int(uid_str)).exists()
        if user and user.active and user.is_platform_guest:
            return user
        return None

    # ------------------------------------------------------------------
    # Soft abuse cap
    # ------------------------------------------------------------------

    def _creation_allowed(self):
        """Whether a new guest may be created under the rolling-window cap."""
        icp = request.env["ir.config_parameter"].sudo()
        now = int(time.time())
        start = int(icp.get_param(GUEST_WINDOW_START_PARAM) or 0)
        count = int(icp.get_param(GUEST_WINDOW_COUNT_PARAM) or 0)
        if now - start > GUEST_WINDOW_SECONDS:
            start, count = now, 0
        if count >= GUEST_WINDOW_MAX:
            return False
        icp.set_param(GUEST_WINDOW_START_PARAM, str(start))
        icp.set_param(GUEST_WINDOW_COUNT_PARAM, str(count + 1))
        return True
