# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from odoo.addons.website_directory.models.website_directory_entry import ZONE_SELECTION

# "canarias" is deliberately absent: it is the value a company carries when it
# belongs to no neighbourhood, and there is no company representing it. Making
# it map to the platform company would be worse than useless -- moving a shop
# INTO "canarias" would then mean "remove the platform company", which owns
# every record on the platform.
ZONE_COMPANY_SELECTION = [
    (key, label) for key, label in ZONE_SELECTION if key != "canarias"
]

# Guard against a sync re-entering through the writes it performs itself.
SKIP_CONTEXT = "skip_zone_company_sync"


class ResCompany(models.Model):
    _inherit = "res.company"

    zone_company_key = fields.Selection(
        selection=ZONE_COMPANY_SELECTION,
        string="Represents commercial zone",
        index=True,
        help="Set on the three zone companies (Guanarteme, Tamaraceite, Lomo "
        "Los Frailes). The products of a merchant of that zone are assigned "
        "to this company as well as to their own, which is what puts them in "
        "the zone shop. Their user accounts are NOT: a zone company in "
        "'Allowed Companies' would let every merchant of the neighbourhood "
        "read and write each other's records.",
    )

    def _zone_companies(self):
        """Every company that stands for a zone. Cheap enough to call often."""
        return (
            self.env["res.company"]
            .sudo()
            .with_context(active_test=False)
            .search([("zone_company_key", "!=", False)])
        )

    def _required_zone_companies(self):
        """The zone companies implied by ``self`` being an owner.

        Expressed as a function of the owners rather than as a diff, so it is
        idempotent and self-healing: running it on an already-correct record
        changes nothing, and running it on a record left half-migrated fixes
        it. A record co-owned by merchants of two different zones correctly
        requires both.
        """
        keys = {
            company.commercial_zone
            for company in self
            if company.commercial_zone and company.commercial_zone != "canarias"
        }
        if not keys:
            return self.env["res.company"].browse()
        return (
            self.env["res.company"]
            .sudo()
            .with_context(active_test=False)
            .search([("zone_company_key", "in", list(keys))])
        )

    @api.model
    def _zone_owners_target(self, owners):
        """What ``owners`` should be once the zone companies are right.

        The zone companies present are not trusted as input: they are dropped
        and recomputed from the real owners. That is what makes a zone change
        remove the old zone without having to remember what it was, and what
        stops a record co-owned by two merchants from losing a zone that the
        other one still needs.
        """
        real_owners = owners - self._zone_companies()
        return real_owners | real_owners._required_zone_companies()

    def _sync_zone_ownership(self):
        """Re-apply the zone companies to everything ``self`` owns.

        Catalogue and people are pulled in opposite directions on purpose: a
        product GAINS the zone company (that is what lists it in the zone
        shop), a user LOSES it (see
        :meth:`res.users._drop_zone_companies`).
        """
        if not self:
            return
        self.env["product.template"]._sync_zone_companies_for_owners(self)
        self.env["res.partner"]._sync_zone_companies_for_owners(self)
        self.env["res.users"]._drop_zone_companies_for_owners(self)

    def write(self, vals):
        res = super().write(vals)
        if "commercial_zone" in vals and not self.env.context.get(SKIP_CONTEXT):
            # The zone the shop moved to is already stored, so the sync reads
            # the new value and the old zone company falls out on its own --
            # no need to capture it before the write.
            self._sync_zone_ownership()
        return res
