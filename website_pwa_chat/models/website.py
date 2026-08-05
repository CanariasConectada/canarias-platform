# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from urllib.parse import urlparse

from odoo import api, fields, models

# Scheme assumed when a website's ``domain`` was typed without one. The field
# is free-form ("E.g. https://www.mydomain.com", website/models/website.py:118)
# and administrators type bare hostnames into it all the time; a link built as
# "canariasconectada.es/chat" would be resolved by the browser as a RELATIVE
# path and silently keep the visitor on the microsite they came from.
DEFAULT_SCHEME = "https"


class Website(models.Model):
    """Which website serves the community chat.

    The platform runs 218 websites off one database: the main portal plus one
    microsite per merchant and per zone. The chat is a property of the PORTAL,
    not of every shop, so every entry point of this module has to answer "is
    this the chat's website?" first.

    A per-website switch is the mechanism, chosen over the two alternatives
    that were on the table:

    - Hardcoding the website id (or the ``base.main_company`` website) would
      make the answer untrue the day the portal is rebuilt or the database is
      restored elsewhere, and it cannot be tested without pinning an id.
    - Deriving it from another module's flag -- ``website.is_marketplace``
      (``website_sale_marketplace``) is the closest thing the platform has to
      "this is the portal" -- would couple the chat to a decision about the
      SHOP. The two happen to coincide today; nothing says they must, and a
      zone microsite may well want its own chat without becoming a
      marketplace.

    So the same shape as ``website_pwa.pwa_enabled``: an explicit boolean,
    default off, visible on the website form. Out of the box no website serves
    ``/chat`` at all; the portal is opted in by hand, once.
    """

    _inherit = "website"

    chat_enabled = fields.Boolean(
        string="Chat de la comunidad",
        help="When enabled, this website serves the community chat at /chat. "
        "Leave it off everywhere except the main portal: the channels are "
        "shared by the whole platform, so serving them from a merchant's "
        "microsite would put another merchant's conversation on their site.",
    )

    chat_link_enabled = fields.Boolean(
        string="Enlace a Comunidad",
        help="When enabled, this website shows a Comunidad entry in its menu "
        "pointing at the chat of the main portal. Meant for the three "
        "neighbourhood portals, which are on their own subdomains: the link "
        "is built as an absolute URL to whichever website actually serves "
        "the chat. A merchant's microsite is a shop window, not a public "
        "square, so leave it off there.",
    )

    @api.model
    def _chat_current(self):
        """Current website, or an empty recordset when the chat is off for it.

        Every route of the module asks this one question, so "is the chat
        served here?" is decided in a single place -- the same arrangement as
        ``website._pwa_current()``.
        """
        website = self.get_current_website()
        return website if website.chat_enabled else self.browse()

    # ------------------------------------------------------------------
    # The menu entry
    # ------------------------------------------------------------------

    @api.model
    def _chat_host_website(self):
        """The website that actually serves the chat, or an empty recordset.

        Derived, never an id. The alternative on the table was "website 1",
        and it is wrong in the only way that matters: a database restored,
        rebuilt or split somewhere else renumbers, and a hardcoded 1 would
        then point the three neighbourhood portals at somebody else's site
        without failing anywhere a test would notice. ``chat_enabled`` is this
        module's own definition of "the site that serves the chat", so asking
        it is asking the question directly.

        ``limit=1``, ordered by id: if two websites are ever switched on, the
        oldest wins and the link stays deterministic rather than alternating.

        sudo: a visitor on a neighbourhood portal cannot read the record of
        another website, and this reads exactly one flag and one domain off
        it -- both of which are about to be printed in a public page anyway.
        """
        return self.sudo().search([("chat_enabled", "=", True)], order="id", limit=1)

    def _chat_menu_url(self):
        """Where this website's "Comunidad" entry points, or False for none.

        Three outcomes, in the order they are decided:

        - The site serves the chat itself: a plain ``/chat``. Same origin, so
          an absolute URL would only break in local and staging deployments.
        - The site was opted in to LINK to it: an absolute URL to the host
          website, because the neighbourhood portals live on their own
          subdomains and a relative ``/chat`` there would 404 on a site that
          does not serve the route.
        - Anything else -- which is the 214 merchant microsites -- False, and
          the template renders nothing at all.

        Returns False rather than raising when the host website is missing or
        its ``domain`` is blank. A menu is not the place to discover that a
        configuration is incomplete: an absent link costs a visitor one tap,
        an exception costs every visitor of that microsite the whole page.
        """
        self.ensure_one()
        if self.chat_enabled:
            return "/chat"
        if not self.chat_link_enabled:
            return False
        host = self._chat_host_website()
        if not host:
            return False
        return self._chat_absolute_url(host, "/chat")

    @staticmethod
    def _chat_absolute_url(host, path):
        """``host.domain`` + ``path``, or False when the domain is unusable.

        ``website.get_base_url()`` is NOT used and that is deliberate: it is
        not overridden on ``website`` in Odoo 19, so it returns the
        system-wide ``web.base.url`` parameter -- the main site's URL only by
        coincidence, and the wrong answer for every other record. The domain
        stored on the record is the only field that really says where that
        website lives.
        """
        domain = (host.sudo().domain or "").strip()
        if not domain:
            return False
        parsed = urlparse(
            domain if "//" in domain else "%s://%s" % (DEFAULT_SCHEME, domain)
        )
        if not parsed.netloc:
            return False
        base = "%s://%s%s" % (
            parsed.scheme or DEFAULT_SCHEME,
            parsed.netloc,
            parsed.path,
        )
        return "%s%s" % (base.rstrip("/"), path)
