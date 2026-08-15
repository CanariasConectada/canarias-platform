# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class WebsiteMenu(models.Model):
    """The navigation bar was simply never in the rollout.

    Reported on 2026-08-15: "veo que no estás traduciendo el menú". It was not
    a failure of the queue -- there was no model for ``website.menu`` at all, so
    "Inicio / Tienda / Comercio / Zonas Comerciales" came out in Spanish under
    ``/en``, ``/de`` and ``/it`` alike. Confirmed in the database: not one menu
    row had a ``de_DE`` or ``it_IT`` entry.

    The menu is the first thing a visitor reads, and the last thing anybody
    thinks to check, because whoever is testing already speaks Spanish.
    """

    _name = "website.menu"
    _inherit = ["website.menu", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["name"]

    def _auto_translate_scoped(self):
        """Menus of a website whose company opted into the rollout.

        A menu with no website is the template Odoo copies for new sites; it is
        never rendered, so translating it would spend the engine on nothing.
        """
        enabled = self.env["res.company"]._auto_translate_companies()
        if not enabled:
            return self.browse()
        websites = self.env["website"].sudo().search([("company_id", "in", enabled.ids)])
        if not websites:
            return self.browse()
        return self.sudo().filtered(lambda menu: menu.website_id in websites)
