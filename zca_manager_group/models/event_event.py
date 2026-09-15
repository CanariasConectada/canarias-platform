# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class EventEvent(models.Model):
    _inherit = "event.event"

    @api.model
    def default_get(self, fields_list):
        """An event created from a zone company lands on the zone website.

        ``website.multi.mixin`` leaves ``website_id`` empty, which means
        "every website": an event organised for Guanarteme would be listed
        on the Tamaraceite site and on the portal too. The zone company has
        one website of its own; default to it. Only a default: the form
        still lets the organiser pick another site or none.
        """
        values = super().default_get(fields_list)
        if "website_id" in fields_list and not values.get("website_id"):
            company = self.env.company
            if company.zone_company_key:
                website = self.env["website"].search(
                    [("company_id", "=", company.id)], limit=1
                )
                if website:
                    values["website_id"] = website.id
        return values
