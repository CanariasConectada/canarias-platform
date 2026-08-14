# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class MultiCompanyAbstract(models.AbstractModel):
    _inherit = "multi.company.abstract"

    def _guard_own_companies(self):
        """A zone is not a shop, so it cannot be the last company standing.

        Merchants belong to their zone company now -- that is what puts their
        catalogue in the zone shop. But it also means the "keep at least one of
        your own companies" guard would accept a product left under the zone
        alone, which takes it out of the merchant's own shop just as surely as
        leaving it under the platform company did. The zone rides along; it
        never substitutes for the shop.
        """
        return super()._guard_own_companies() - self.env["res.company"]._zone_companies()
