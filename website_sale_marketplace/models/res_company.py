# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import models

_logger = logging.getLogger(__name__)


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        """Sweep marketplace links when a merchant is archived.

        Archiving a merchant used to leave its products on the aggregated
        shop: the backfill had linked the portal company into their
        ``company_ids``, and the portal's record rule reads that link, not
        the owner's active flag. It took a manual SQL sweep every time a
        business left the platform (101racing on 2026-08-11 was the latest).

        Now the archival does it itself: after the write, any product whose
        every active real owner is gone loses its portal/zone marketplace
        links, so the record rule stops showing it — automatically, for every
        future retirement.
        """
        archiving = vals.get("active") is False
        res = super().write(vals)
        if archiving and self:
            self.env["product.template"]._wsm_sweep_orphaned_marketplace_links()
        return res
