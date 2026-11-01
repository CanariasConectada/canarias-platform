# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

from .res_users import GROUP_XMLID


class EventEvent(models.Model):
    _inherit = "event.event"

    def _is_zone_manager(self):
        return self.env.user.has_group(GROUP_XMLID)

    @api.model
    def default_get(self, fields_list):
        """An event created from a zone company lands on the zone website.

        ``website.multi.mixin`` leaves ``website_id`` empty, which means
        "every website": an event organised for Guanarteme would be listed
        on the Tamaraceite site and on the portal too. The zone company has
        one website of its own; default to it. Only a default: the form
        still lets the organiser pick another site or none.

        For a zone manager the company is not a default but the rule:
        core's company rule accepts an event with no company, which every
        zone could then edit, so ``company_id`` is forced (here and in
        ``create``) to the manager's zone.
        """
        values = super().default_get(fields_list)
        company = self.env.company
        if "company_id" in fields_list and self._is_zone_manager():
            values["company_id"] = company.id
        if "website_id" in fields_list and not values.get("website_id"):
            if company.zone_company_key:
                website = self.env["website"].search(
                    [("company_id", "=", company.id)], limit=1
                )
                if website:
                    values["website_id"] = website.id
        return values

    @api.model_create_multi
    def create(self, vals_list):
        if self._is_zone_manager():
            for vals in vals_list:
                if not vals.get("company_id"):
                    vals["company_id"] = self.env.company.id
        return super().create(vals_list)
