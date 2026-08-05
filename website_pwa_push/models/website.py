# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class Website(models.Model):
    _inherit = "website"

    pwa_push_enabled = fields.Boolean(
        string="Avisos push",
        help="When enabled, visitors of this website can allow notifications "
        "and receive chat messages while the site is closed. Independent "
        "from the app switch on purpose: the app can be installable "
        "everywhere while push is piloted on a single website.",
    )

    def _pwa_push_active(self):
        """Is Web Push really on for this website?

        Two switches, one question, asked in a single place -- the controller
        that builds the worker and the layout hook that advertises push to the
        page must never disagree.

        ``pwa_push_enabled`` alone means nothing: the push handlers live inside
        the service worker, and ``/service-worker.js`` answers 404 when
        ``pwa_enabled`` is off (``website_pwa``'s ``_pwa_current``). Without
        the app there is no worker to receive a push, so a website with push on
        and the app off is exactly as silent as one with both off.

        Deliberately no ``ensure_one``: this is called from ``website.layout``,
        where an empty ``website`` recordset has to answer "no" rather than
        raise a singleton error in the middle of rendering a public page. Field
        access on an empty recordset already reads as ``False``.
        """
        return bool(self.pwa_enabled and self.pwa_push_enabled)
