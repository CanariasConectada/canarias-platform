# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, api, models

from .res_company import SKIP_CONTEXT


class ZoneCompanyOwnershipMixin(models.AbstractModel):
    """Records that must carry the zone company of whoever owns them.

    A merchant's product belongs to the merchant, to the platform, and -- from
    now on -- to the company that stands for the merchant's neighbourhood.
    That last one is what puts it in the zone shop, and it has to follow the
    merchant around: change the shop's zone and its catalogue moves with it.
    """

    _name = "zone.company.ownership.mixin"
    _description = "Ownership follows the owner's commercial zone"

    @api.model
    def _sync_zone_companies_for_owners(self, companies):
        """Fix every record owned by ``companies``."""
        if not companies:
            return self.browse()
        records = (
            self.sudo()
            .with_context(active_test=False)
            .search([("company_ids", "in", companies.ids)])
        )
        return records._apply_zone_companies()

    def _zone_sync_candidates(self):
        """The records of ``self`` a zone may legitimately be applied to."""
        return self

    def _apply_zone_companies(self):
        """Recompute the zone companies of these records from their owners."""
        Company = self.env["res.company"]
        changed = self.browse()
        for record in self.sudo()._zone_sync_candidates():
            owners = record.company_ids
            target = record._zone_owners_floor(Company._zone_owners_target(owners))
            if target == owners:
                continue
            record.with_context(**{SKIP_CONTEXT: True}).company_ids = [
                Command.set(target.ids)
            ]
            changed |= record
        return changed

    def _zone_owners_floor(self, target):
        """Companies that must survive the recomputation regardless.

        The recomputation drops every zone company and re-derives them, which
        is what makes it idempotent -- but a record whose own company IS a
        zone company would lose itself. Overridden where that can happen.
        """
        return target
