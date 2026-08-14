# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo.addons.website.controllers.main import Website


class WebsiteSwitchSameDomain(Website):
    def website_force(self, website_id, path="/", isredir=False, **kw):
        """Switch website without leaving the domain the editor is open on.

        Core sends the browser to ``website.domain`` first and only then forces
        the website, because a different domain means a different session (see
        ``website/controllers/main.py``). With 218 websites, each with its own
        domain, that turns "look at another site" into a full domain hop: the
        editor is left behind, the session is re-established elsewhere, and the
        user is somewhere they did not ask to be.

        ``isredir=True`` is core's own way of saying "the domain part is
        already done" -- the same value it passes itself on the second leg of
        the hop -- so forcing it here skips the hop and keeps everything else,
        including the permission check above it, exactly as core wrote it.

        Requested on 2026-08-14: "el switch que está en editar sitio web [...]
        no lo quiero, desactiva esa redirección".
        """
        return super().website_force(website_id, path=path, isredir=True, **kw)
