# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ResPartner(models.Model):
    """The shop's own description, which is written from the contact form.

    Every merchant microsite renders it, and it was outside the rollout: the
    products of a shop came out in German while the paragraph introducing the
    shop stayed in Spanish.
    """

    _name = "res.partner"
    _inherit = ["res.partner", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["website_description", "website_short_description"]

    def _auto_translate_scoped(self):
        """The contact a company publishes as itself, nothing else.

        Deliberately narrow. A partner table holds customers and suppliers as
        well, and none of that is public content -- translating it would spend
        the engine on private data and put personal names through a machine.
        """
        enabled = self.env["res.company"]._auto_translate_companies()
        if not enabled:
            return self.browse()
        published = set(enabled.sudo().mapped("partner_id").ids)
        return self.sudo().filtered(lambda partner: partner.id in published)
