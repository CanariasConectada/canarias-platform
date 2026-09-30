# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

from ..controllers.main import COMMUNITY_PATH


class Website(models.Model):
    """Point the "Comunidad" menu entry at the door instead of the pages.

    Only :meth:`_chat_menu_url` is overridden. ``_chat_support_url`` -- the
    floating button -- is inherited untouched: support still lives at
    ``/chat/soporte`` and this module retires the community pages only.
    """

    _inherit = "website"

    def _chat_menu_url(self):
        """Where the "Comunidad" entry points now: /community.

        A rewrite of the parent, not a call to it: the parent hardcodes its
        own ``/chat`` path, and string-replacing its answer would couple this
        module to that spelling. The SHAPE is the parent's, decision for
        decision (read the long rationale there):

        - ``chat_link_enabled`` still gates the entry on every website;
        - the website that serves the chat links relatively, because on the
          same origin an absolute URL is only ever wrong (local, staging);
        - a linked-only website (the zone portals on their own subdomains)
          gets an absolute URL to the host website via the parent's own
          ``_chat_absolute_url``, so the two modules can never disagree
          about how a domain becomes a link;
        - False, never an exception, when the host or its domain is missing.

        The host is still resolved from ``chat_enabled`` even though the page
        it used to mark is now a redirect: /community is served by every
        website, but the sessions it mints (guest door, signup, /odoo) live
        on the PORTAL's domain, so cross-subdomain entries must keep landing
        the visitor there and not on a card whose session would be stranded
        on a microsite.
        """
        self.ensure_one()
        if not self.chat_link_enabled:
            return False
        if self.chat_enabled:
            return COMMUNITY_PATH
        host = self._chat_host_website()
        if not host:
            return False
        return self._chat_absolute_url(host, COMMUNITY_PATH)
