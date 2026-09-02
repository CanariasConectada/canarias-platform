# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from .res_company import SKIP_CONTEXT


class ResPartner(models.Model):
    _name = "res.partner"
    _inherit = ["res.partner", "zone.company.ownership.mixin"]

    # Same field as on the product, declared per concrete model because the
    # default relation table name would collide with the one ``company_ids``
    # already occupies between this model and ``res.company``.
    zone_company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="res_partner_zone_company_rel",
        column1="partner_id",
        column2="company_id",
        string="Commercial Zone",
        compute="_compute_zone_company_ids",
        store=True,
        help="The zone companies among this contact's owners. Derived from "
        "the owning shop's commercial zone; group or filter by it to see a "
        "neighbourhood's contacts together.",
    )

    @api.depends("company_ids", "company_ids.zone_company_key")
    def _compute_zone_company_ids(self):
        return super()._compute_zone_company_ids()

    def _zone_owners_floor(self, target):
        """The zone's own people keep their zone company.

        The recomputation drops every zone company and re-derives them from
        the owners' ``commercial_zone``. A contact whose OWN company IS a
        zone company -- the zone's contact card, the card behind a zone
        staff account -- would be stripped down to nothing and turn global,
        which is the opposite of what the guard wants. Mirrors
        ``res.users._zone_company_holders``.
        """
        target = super()._zone_owners_floor(target)
        zones = self.env["res.company"]._zone_companies()
        if self.company_id and self.company_id in zones:
            target |= self.company_id
        return target

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        if not self.env.context.get(SKIP_CONTEXT):
            partners._apply_zone_companies()
        return partners

    def write(self, vals):
        res = super().write(vals)
        # Only an ownership edit can change which zone applies -- the same
        # gate the product uses, and for the same reason: reacting to every
        # write would re-derive the whole address book on every typo fix.
        if ("company_ids" in vals or "company_id" in vals) and not self.env.context.get(
            SKIP_CONTEXT
        ):
            self._apply_zone_companies()
        return res
