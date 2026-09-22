# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import http
from odoo.http import request

from odoo.addons.website_pwa_chat.controllers.main import WebsiteChat

# The one place the redirects lead to. discuss_community's door routes by
# identity itself (internal -> /odoo, everybody else -> the card), so this
# module never has to ask who is knocking before pointing them there.
COMMUNITY_PATH = "/community"


class WebsiteChatCommunityRedirect(WebsiteChat):
    """Retire the standalone community pages behind the /community door.

    Only the two COMMUNITY pages are overridden. Everything else on the
    parent controller is the SUPPORT feature and is inherited untouched:
    ``/chat/soporte`` and ``/chat/soporte/identificarme`` (the full page,
    the floating window and its lazy iframe all navigate there), and the
    ``/website_pwa_chat/messages`` / ``/website_pwa_chat/pending`` jsonrpc
    routes that give the support conversation its live half.

    Bare ``@http.route()`` on both overrides: the routing kwargs (``type``,
    ``auth``, ``website``, ``sitemap``) are inherited from the parent rule,
    so the two URL shapes cannot drift from the ones being retired.
    """

    @http.route()
    def chat_index(self, **kwargs):
        """301 to the door instead of the channel list.

        The website gate is kept: the standalone page only ever existed on
        the website(s) with ``chat_enabled`` and answered 404 everywhere
        else. A redirect that fired on all 218 sites would turn a
        deliberate "this site does not serve the chat" into a live URL on
        every merchant's storefront.

        301 and not 302 on purpose: the page is retired, not moved aside,
        and shared links, crawlers and pinned PWAs should relearn the
        address once. No guest is created on the way out -- the parent
        never created one here either, and an anonymous hit that only
        bounces must not leave a ``mail.guest`` row behind.
        """
        if not request.env["website"]._chat_current():
            return request.not_found()
        return request.redirect(COMMUNITY_PATH, code=301)

    @http.route()
    def chat_channel(self, channel_id, **kwargs):
        """301 to the door instead of one channel's page.

        ``channel_id`` is deliberately not resolved: whether the channel
        exists, is published or is visible to this caller no longer matters
        on a retired page, and answering the question would mean creating a
        guest just to say "go to the door". Every old deep link -- valid,
        stale or guessed -- lands on /community, where who-may-see-what is
        decided by the Discuss backend the visitor is routed into.

        The support conversation loses nothing here. Its address is the
        literal /chat/soporte (untouched, it ranks above this converter
        rule), and its live half rides the jsonrpc routes, which still
        resolve numeric ids through ``_website_chat_channel`` themselves.
        The one thing retired with the page is the page-shaped alias
        /chat/<own support id>, which nothing ever linked to.
        """
        if not request.env["website"]._chat_current():
            return request.not_found()
        return request.redirect(COMMUNITY_PATH, code=301)
