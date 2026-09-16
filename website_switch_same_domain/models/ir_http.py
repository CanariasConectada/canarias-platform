# Copyright 2026 Canarias Conectada
# License AGPL-3 - See http://www.gnu.org/licenses/agpl-3.0.html

from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        """Tell the editor's website switcher to stay on the domain it is on.

        The controller override in this module was only half the story, and
        the half nobody reaches. Picking a site from the switcher never gets
        as far as `/website/force`: the systray component sends the whole
        browser away first --

            website_switcher_systray_item.js
            if (!session.website_bypass_domain_redirect && website.domain
                && !isHTTPSorNakedDomainRedirection(...)) {
                window.location.href = url;   // the other domain
            } else {
                this.websiteService.goToWebsite({...});   // stays put
            }

        -- so with 218 sites, each with a domain of its own, every switch was
        a domain hop no matter what the server was willing to do. Reported
        twice: "no lo quiero, desactiva esa redirección" (2026-08-14) and "lo
        estás volviendo a hacer" (2026-08-17), the second time after the
        controller had been verified working, which is exactly what a fix on
        the wrong side of the wire looks like.

        `website_bypass_domain_redirect` is core's own switch for this. It is
        read and never written anywhere in the codebase -- a hook left for
        support -- and turning it on sends the component down its `else`
        branch, which asks the server instead of the browser. That is where
        the controller finally gets its say: it forces the website in the
        session that is already open, on the domain the editor is already on.

        Core's comment on the flag says "bugs to be expected", and the reason
        is real: a different domain means a different session, so a website
        forced here would not be forced over there. It does not apply to this
        platform -- the 218 domains are subdomains of one, sharing the session
        cookie -- and the pair has been verified end to end on a copy of
        production, 216 of 216 sites reached without leaving the domain.
        """
        info = super().session_info()
        info["website_bypass_domain_redirect"] = True
        return info
