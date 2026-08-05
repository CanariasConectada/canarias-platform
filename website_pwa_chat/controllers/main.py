# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, http
from odoo.http import request

from odoo.addons.mail.tools.discuss import add_guest_to_context

# Where the "create your account" call to action points when free signup is
# open, and where it points when it is not. Both are core routes; the choice
# is made server side because a signup link that lands on "signup is disabled"
# is worse than no signup link.
SIGNUP_URL = "/web/signup"
LOGIN_URL = "/web/login"

# How long the held card tells its author a review usually takes. Read from
# `discuss_channel_moderation`'s own system parameter -- the threshold at which
# that module emails the moderators about a message nobody has looked at -- so
# the promise on the page and the promise the operation actually keeps are ONE
# number. Restating "media hora" in the copy would have been warmer to read and
# wrong the first time somebody moved the threshold, which is exactly the kind
# of drift the first internal users are going to notice.
#
# Referenced as a plain string, with a fallback, rather than imported: this
# module must keep rendering if the parameter is deleted, set to garbage, or
# never shipped at all.
REVIEW_DELAY_PARAM = "discuss_channel_moderation.late_alert_minutes"
REVIEW_DELAY_DEFAULT_MINUTES = 30


class WebsiteChat(http.Controller):
    """The chat surface of the app: two pages, one JSON catch-up route.

    All three start with the same two questions, in this order:

    1. Does THIS website serve the chat (``website._chat_current()``)? The
       platform runs 218 sites off one database and the channels belong to the
       portal, so anything else answers 404 -- not an empty page, which would
       leave a dead menu entry on 217 microsites.
    2. May THIS visitor see the channel? Answered by a ``search()`` run as the
       visitor, i.e. by ``ir_rule_discuss_channel_all``. Never by this file.
    """

    # ------------------------------------------------------------------
    # Pages
    # ------------------------------------------------------------------

    @http.route("/chat", type="http", auth="public", website=True, sitemap=False)
    @add_guest_to_context
    def chat_index(self, **kwargs):
        """The channel list.

        No guest is created here. Reading which conversations exist is not
        participating in any of them, and every anonymous hit -- crawlers
        included -- would otherwise leave a ``mail.guest`` row behind.

        ``sitemap=False``: the page is the app's chat, it has no standalone
        content to index, and its per-channel URLs are only meaningful to
        somebody who is already in the app.
        """
        website = request.env["website"]._chat_current()
        if not website:
            return request.not_found()
        return request.render(
            "website_pwa_chat.chat_index",
            {
                "channels": request.env["discuss.channel"]._website_chat_channels(),
                **self._chat_visitor_values("/chat"),
            },
        )

    @http.route(
        "/chat/<int:channel_id>",
        type="http",
        auth="public",
        website=True,
        sitemap=False,
    )
    @add_guest_to_context
    def chat_channel(self, channel_id, **kwargs):
        """One channel: its messages, the composer, and the visitor's own
        messages still waiting for review.

        ON THE URL, because it looks like a collision and is not. ``mail``
        already owns ``/chat/<string:create_token>``
        (``mail/controllers/discuss/public_page.py:14-24``). Werkzeug does not
        resolve that by registration order: it sorts rules by converter weight,
        and ``NumberConverter.weight`` is 50 against ``UnicodeConverter``'s 100
        (``werkzeug/routing/converters.py``), so an all-digits segment matches
        the ``int`` rule and everything else still reaches core's. Verified
        against the werkzeug actually installed here (3.0.1) rather than
        assumed. Core's route is dormant anyway -- it 404s unless the
        ``mail.chat_from_token`` config parameter is set -- but the ordering is
        what makes ``/chat/12`` unambiguous, not that.

        A slug (``<model("discuss.channel"):channel>``) was the alternative and
        was refused: it puts the channel NAME in the URL, and the four channels
        are renameable from the Discuss UI by anybody with write access, so
        every shared link would rot on the first rename. The id is stable and
        the name is on the page.
        """
        website = request.env["website"]._chat_current()
        if not website:
            return request.not_found()
        channel = request.env["discuss.channel"]._website_chat_channel(channel_id)
        if not channel:
            return request.not_found()
        # Identity BEFORE anything is read or rendered. The cookie has to be on
        # the response that carries the page, because the page's websocket
        # subscription is what picks it up (``mail`` decorates
        # ``ir.websocket._subscribe`` with ``add_guest_to_context`` and appends
        # the guest to the bus channel list,
        # ``mail/models/discuss/ir_websocket.py:27-29``). Set it any later --
        # on the post, say -- and the connection is already open without it, so
        # the author would never be told their message was approved.
        self._chat_ensure_guest()
        # Re-resolved rather than reused: ``_set_auth_cookie`` rebinds
        # ``request.env`` with the guest in context, and everything below --
        # "is this message mine", "which held rows are mine" -- reads that
        # persona. The recordset captured a moment ago still points at the
        # env without it. Going back through the same helper also keeps the
        # record rule in the picture instead of browsing around it.
        channel = request.env["discuss.channel"]._website_chat_channel(channel_id)
        messages = channel._website_chat_messages()
        return request.render(
            "website_pwa_chat.chat_channel",
            {
                "channel": channel,
                "messages": channel._website_chat_message_values(messages),
                "pending": channel._website_chat_pending(),
                **self._chat_visitor_values(self._chat_channel_url(channel)),
            },
        )

    # ------------------------------------------------------------------
    # Live catch-up
    # ------------------------------------------------------------------

    @http.route(
        "/website_pwa_chat/messages",
        type="jsonrpc",
        auth="public",
        website=True,
        readonly=True,
    )
    @add_guest_to_context
    def chat_messages(self, channel_id, after=None):
        """Messages newer than ``after``, in the page's own flat shape.

        The bus tells the page THAT something happened; it does not tell it
        what, because the payload core broadcasts
        (``discuss.channel/new_message``) is a ``Store`` graph for the backend
        Discuss client. This route is the "what": same access path as the
        page, same four fields, no second format to keep in sync.

        ``readonly=True`` because it really is: it creates no guest (the page
        did that) and writes nothing. A message-list poll must never be the
        thing that takes a read/write cursor.
        """
        if not request.env["website"]._chat_current():
            return {"messages": []}
        channel = request.env["discuss.channel"]._website_chat_channel(channel_id)
        if not channel:
            return {"messages": []}
        messages = channel._website_chat_messages(after=after and int(after))
        return {"messages": channel._website_chat_message_values(messages)}

    @http.route(
        "/website_pwa_chat/pending",
        type="jsonrpc",
        auth="public",
        website=True,
        readonly=True,
    )
    @add_guest_to_context
    def chat_pending(self, channel_id):
        """The caller's own held messages, as the page's own HTML fragment.

        Returns markup rather than data so that the wording of the invitation
        to register lives in exactly ONE place, the QWeb template. The
        alternative -- shipping the strings to the frontend and rebuilding the
        block in JavaScript -- would have put the most important paragraph of
        the product in two files that nothing keeps in step.

        There is no leak in rendering server side for an anonymous caller:
        ``_website_chat_pending`` resolves the persona itself and answers empty
        for anybody without one, and the template renders nothing at all when
        the list is empty.
        """
        if not request.env["website"]._chat_current():
            return {"html": ""}
        channel = request.env["discuss.channel"]._website_chat_channel(channel_id)
        if not channel:
            return {"html": ""}
        html = request.env["ir.qweb"]._render(
            "website_pwa_chat.chat_pending",
            {
                "pending": channel._website_chat_pending(),
                **self._chat_visitor_values(self._chat_channel_url(channel)),
            },
        )
        return {"html": str(html)}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chat_ensure_guest(self):
        """Give an anonymous visitor an identity of their own, once.

        Without it every anonymous request IS the same persona -- the shared
        ``base.public_partner`` -- and the moderation module has nowhere
        private to send "your message is being reviewed". A guest is the
        smallest identity that fixes that: no account, no email, one httpOnly
        cookie.

        Reuses core's own creator so the cookie name, format, lifetime and
        context update stay core's business
        (``mail/models/discuss/mail_guest.py:70-81``). It is a no-op when the
        request already carries a valid guest cookie.

        sudo: ``mail.guest`` has no create ACL for the public user; this is the
        same sudo core uses on ``/discuss/channel/<id>``
        (``mail/controllers/discuss/public_page.py:99-104``).
        """
        if not request.env.user._is_public():
            return request.env["mail.guest"]
        guest_model = request.env["mail.guest"]
        return guest_model.sudo()._get_or_create_guest(
            guest_name=_("Visitante"),
            country_code=request.geoip.country_code,
            timezone=guest_model._get_timezone_from_request(request),
        )

    @staticmethod
    def _chat_channel_url(channel):
        """Where a visitor should land back after logging in or signing up."""
        return "/chat/%s" % channel.id

    def _chat_visitor_values(self, redirect):
        """What the templates need to know about who is reading.

        ``is_visitor`` drives the whole conversion story: the invitation to
        register is addressed to people who have no account, and showing it to
        somebody who is logged in would be noise at best.

        ``redirect`` is passed in rather than read from
        ``request.httprequest.path`` because the same values are built for the
        JSON fragment route, whose path is ``/website_pwa_chat/pending`` -- a
        visitor sent back THERE after signing up would land on a bare JSON
        error instead of the conversation they were writing in.
        """
        return {
            "is_visitor": request.env.user._is_public(),
            "register_url": self._chat_register_url(redirect),
            "login_url": "%s?redirect=%s" % (LOGIN_URL, redirect),
            "review_minutes": self._chat_review_minutes(),
        }

    @staticmethod
    def _chat_review_minutes():
        """The wait the page is allowed to promise, in minutes.

        Defensive on purpose: an unreadable or absent parameter must produce
        the default sentence, never an exception on a page whose whole job at
        that moment is to reassure somebody.
        """
        raw = (
            request.env["ir.config_parameter"]
            .sudo()
            .get_param(REVIEW_DELAY_PARAM, REVIEW_DELAY_DEFAULT_MINUTES)
        )
        try:
            minutes = int(raw)
        except (TypeError, ValueError):
            return REVIEW_DELAY_DEFAULT_MINUTES
        return minutes if minutes > 0 else REVIEW_DELAY_DEFAULT_MINUTES

    def _chat_register_url(self, redirect):
        """Where "crear mi cuenta" goes, decided by whether it can work.

        ``auth_signup`` is always installed (``website`` depends on it) but
        free signup is a setting, and when it is off ``/web/signup`` bounces to
        the login page with an error. Asking the setting here means the button
        never promises something the database refuses.
        """
        users = request.env["res.users"].sudo()
        scope = getattr(users, "_get_signup_invitation_scope", None)
        if scope and scope() == "b2c":
            return "%s?redirect=%s" % (SIGNUP_URL, redirect)
        return "%s?redirect=%s" % (LOGIN_URL, redirect)
