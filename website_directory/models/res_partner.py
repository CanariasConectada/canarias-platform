# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

from .res_company import PARTNER_SYNC_FIELDS


class ResPartner(models.Model):
    _inherit = "res.partner"

    def write(self, vals):
        """Flag the linked companies for a directory resync.

        The directory entry copies partner fields (phone, email, street,
        city, vat) at every sync. ``res.company.write`` only flags the
        company when those keys are written *through the company form*; a
        partner edited directly (Contacts, l10n, programmatic code) would
        otherwise never mark its company pending and the public entry would
        show stale data. This override closes that gap.
        """
        res = super().write(vals)
        if PARTNER_SYNC_FIELDS.intersection(vals):
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
