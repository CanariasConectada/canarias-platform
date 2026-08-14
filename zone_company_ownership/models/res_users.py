# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

from .res_company import SKIP_CONTEXT


class ResUsers(models.Model):
    _name = "res.users"
    _inherit = ["res.users", "zone.company.ownership.mixin"]

    def _zone_owners_floor(self, target):
        """A user never loses the company they are logged into.

        The recomputation drops every zone company before re-deriving them,
        and the staff OF a zone are exactly the users whose own company is a
        zone company. Without this they would be stripped of it, and core's
        own check ("the chosen company is not in the allowed companies for
        this user") would reject the write -- or worse, let it through and
        leave someone unable to log in anywhere.
        """
        target = super()._zone_owners_floor(target)
        return target | self.company_id

    @api.model_create_multi
    def create(self, vals_list):
        users = super().create(vals_list)
        if not self.env.context.get(SKIP_CONTEXT):
            users._apply_zone_companies()
        return users

    def write(self, vals):
        res = super().write(vals)
        if ("company_ids" in vals or "company_id" in vals) and not self.env.context.get(
            SKIP_CONTEXT
        ):
            self._apply_zone_companies()
        return res
