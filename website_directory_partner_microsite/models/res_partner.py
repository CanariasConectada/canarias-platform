# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        """A new trade name must reach the directory card.

        The card shows ``res.company.microsite_title``, which falls back to
        the trade name -- and the trade name is ``res.partner.comercial``
        (``l10n_es_partner``), edited from Contacts as often as from the
        company form. ``website_directory`` flags the company for a resync
        from its own ``PARTNER_SYNC_FIELDS`` constant and exposes no hook for
        other partner fields, so this override does for ``comercial`` what
        the base does for phone or street, rather than mutating the base
        module's constant from here.
        """
        res = super().write(vals)
        if "comercial" in vals:
            companies = (
                self.env["res.company"]
                .sudo()
                .with_context(active_test=False)
                .search([("partner_id", "in", self.ids)])
            )
            companies.filtered(lambda c: not c.directory_sync_pending).write(
                {"directory_sync_pending": True}
            )
        return res
