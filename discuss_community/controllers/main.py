# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import hmac as hmac_lib
import logging
import secrets
import time

from odoo import http
from odoo.http import request

from odoo.addons.auth_signup.controllers.main import AuthSignupHome
from odoo.addons.web.controllers.home import Home

# Reused, not copied: the open-redirect guard is website_login_branding's and
# a second spelling of it would be a second place to patch.
from odoo.addons.website_login_branding.controllers.main import GuestAccess

try:  # Odoo's helper keys the HMAC with `database.secret` and adds a scope.
    from odoo.tools.misc import hmac as odoo_hmac
except ImportError:  # pragma: no cover - stripped-down build without the helper
    odoo_hmac = None

_logger = logging.getLogger(__name__)

# Signed reuse cookie for community guests: value is "<uid>.<hmac>". Its own
# name and its own HMAC scope, distinct from website_login_branding's portal
# guest cookie: the two populations must never validate each other's cookies
# (a portal guest cookie must not mint an internal session, ever).
COMMUNITY_GUEST_COOKIE = "cc_community_guest"
COMMUNITY_GUEST_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days
COMMUNITY_GUEST_HMAC_SCOPE = "discuss_community.guest"

# Soft abuse cap, same rolling-window design as /guest/enter: repeat visitors
# ride their signed cookie and never create a user, so this only throttles a
# flood of BRAND-NEW anonymous sessions. Separate counters from the portal
# guest cap -- the two doors are throttled independently.
COMMUNITY_GUEST_WINDOW_SECONDS = 60 * 60  # 1 hour window
COMMUNITY_GUEST_WINDOW_MAX = 200  # new guests per window before refusal
COMMUNITY_GUEST_WINDOW_START_PARAM = "discuss_community.guest_window_start"
COMMUNITY_GUEST_WINDOW_COUNT_PARAM = "discuss_community.guest_window_count"


def _arrival_zone(controller):
    """The commercial zone of the website serving the current request.

    Website-of-arrival is the product decision for NEW community members: the
    site you walked in through decides the neighbourhood channel you start in.
    Source of truth is ``website.company_id.commercial_zone``
    (``res_company_zone``); ``canarias`` -- the platform's own sites -- means
    "no neighbourhood" and lands the user in the general channel only.

    Resolution: ``request.website`` when the route is website-bound (both
    routes below and ``/web/signup`` are), else ``website_login_company``'s
    ``_find_login_website`` -- the Host-header-safe resolver, available on the
    merged ``Home`` controller because that module is a dependency. Never a
    hand-rolled ``domain ilike host`` search: that exact shortcut let a
    client-controlled Host header pick the wrong website once already.
    """
    website = getattr(request, "website", None)
    if not website:
        finder = getattr(controller, "_find_login_website", None)
        website = finder() if finder else None
    company = website.sudo().company_id if website else None
    if not company:
        return False
    return request.env["res.company"].sudo()._normalise_zone(company.commercial_zone)


class CommunitySignup(AuthSignupHome):
    """Flag website signups so the model layer promotes them to community."""

    def do_signup(self, qcontext, do_login=True):
        """Mark UNINVITED signups served by a website as community signups.

        The promotion itself lives in ``res.users._signup_create_user`` (the
        model must stay the place where the account shape is decided); this
        override only answers the two questions a controller can answer and a
        model cannot: "is this request served by a website?" and "which one?".

        Token signups are exempt here AND re-checked in the model: an invited
        user was invited as portal by someone in the backend, and the web
        page they redeem the invitation on must not overrule that person.
        """
        if not qcontext.get("token") and getattr(request, "website", None):
            request.update_context(
                community_signup=True,
                community_signup_zone=_arrival_zone(self),
            )
        return super().do_signup(qcontext, do_login=do_login)


class CommunityAccess(Home):
    """The /community landing page and the internal-guest door."""

    @http.route(
        "/community",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    def community_landing(self, **kw):
        """Route by who you already are; offer the two doors to anyone else.

        * Internal session (community member, merchant staff, admin): the
          community lives in the Discuss backend now, go there.
        * Other authenticated session (portal merchant, portal guest): the
          legacy website chat is still their community surface in Phase 1.
        * Anonymous: the minimal page with the two entries -- guest button
          (POST, one click) and account creation (signup).
        """
        if request.session.uid:
            user = request.env["res.users"].sudo().browse(request.session.uid)
            if user.exists() and not user.share:
                return request.redirect("/odoo")
            return request.redirect("/chat")
        return request.render("discuss_community.community_landing", {})

    @http.route(
        "/community/guest",
        type="http",
        auth="public",
        methods=["POST"],
        website=True,
        sitemap=False,
    )
    def community_guest_enter(self, redirect=None, **kw):
        """Log the visitor in as a reusable INTERNAL community guest.

        The same five steps, in the same order and for the same reasons, as
        ``website_login_branding``'s ``/guest/enter`` (see the long rationale
        there); what differs is what the account IS (internal + community, so
        the session lands in the Discuss backend) and therefore the default
        target: ``/odoo``.

        POST-only + the framework's CSRF check: a route that mints accounts
        must never be reachable by a prefetcher following a link.
        """
        target = redirect if GuestAccess._is_safe_local_path(redirect) else "/odoo"

        if request.session.uid:
            # Never spawn or swap an account under an authenticated session.
            return request.redirect(target)

        user = self._resolve_community_cookie_guest()
        if not user:
            if not self._community_creation_allowed():
                _logger.warning(
                    "discuss_community: guest creation throttled (from %s)",
                    request.httprequest.remote_addr,
                )
                # Degrade to anonymous browsing rather than 500. Not to
                # `target`: /odoo would bounce an anonymous session to the
                # login page, which reads as an error, not as a soft cap.
                return request.redirect("/")
            zone = _arrival_zone(self)
            user = request.env["res.users"].sudo()._create_community_guest(zone=zone)

        # Fresh throwaway password on every entry; never stored or logged.
        password = secrets.token_urlsafe(24)
        user.sudo().write({"password": password})
        request.session.authenticate(
            request.env,
            {"login": user.login, "type": "password", "password": password},
        )

        response = request.redirect(target)
        response.set_cookie(
            COMMUNITY_GUEST_COOKIE,
            self._sign_community_guest(user.id),
            max_age=COMMUNITY_GUEST_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
            secure=request.httprequest.is_secure,
        )
        return response

    # ------------------------------------------------------------------
    # Signed reuse cookie
    # ------------------------------------------------------------------

    def _sign_community_guest(self, uid):
        """Return the signed cookie value ``"<uid>.<hmac>"`` for ``uid``."""
        return "%s.%s" % (uid, self._community_guest_hmac(uid))

    def _community_guest_hmac(self, uid):
        """HMAC-SHA256 over ``uid``, keyed by ``database.secret``, OUR scope.

        The scope is what stops a ``cc_guest`` cookie signed by
        website_login_branding from validating here (and vice versa): same
        secret, different message domain, different signatures.
        """
        message = str(uid)
        if odoo_hmac is not None:
            return odoo_hmac(request.env(su=True), COMMUNITY_GUEST_HMAC_SCOPE, message)
        secret = (
            request.env["ir.config_parameter"].sudo().get_param("database.secret") or ""
        )
        return hmac_lib.new(
            secret.encode(), message.encode(), hashlib.sha256
        ).hexdigest()

    def _resolve_community_cookie_guest(self):
        """The guest a VALID signed cookie points to, or ``None``.

        Same trust chain as the portal-guest resolver: HMAC first
        (constant-time, over the whole cookie), then existence, activity and
        the ``is_community_guest`` flag -- a repurposed or promoted account
        must not be handed a session by an old cookie. The flag check is
        doing MORE work here than in the portal version: the uid in this
        cookie unlocks an INTERNAL session, so "still a guest" is the line
        between reuse and privilege escalation.
        """
        cookie = request.httprequest.cookies.get(COMMUNITY_GUEST_COOKIE)
        if not cookie or "." not in cookie:
            return None
        uid_str, _sep, _mac = cookie.partition(".")
        if not uid_str.isdigit():
            return None
        if not hmac_lib.compare_digest(
            cookie, self._sign_community_guest(int(uid_str))
        ):
            return None
        user = request.env["res.users"].sudo().browse(int(uid_str)).exists()
        if user and user.active and user.is_community_guest:
            return user
        return None

    # ------------------------------------------------------------------
    # Soft abuse cap
    # ------------------------------------------------------------------

    def _community_creation_allowed(self):
        """Whether a new guest may be created under the rolling-window cap."""
        icp = request.env["ir.config_parameter"].sudo()
        now = int(time.time())
        start = int(icp.get_param(COMMUNITY_GUEST_WINDOW_START_PARAM) or 0)
        count = int(icp.get_param(COMMUNITY_GUEST_WINDOW_COUNT_PARAM) or 0)
        if now - start > COMMUNITY_GUEST_WINDOW_SECONDS:
            start, count = now, 0
        if count >= COMMUNITY_GUEST_WINDOW_MAX:
            return False
        icp.set_param(COMMUNITY_GUEST_WINDOW_START_PARAM, str(start))
        icp.set_param(COMMUNITY_GUEST_WINDOW_COUNT_PARAM, str(count + 1))
        return True
