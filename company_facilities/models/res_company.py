# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    facility_ids = fields.Many2many(
        "company.facility",
        "res_company_facility_rel",
        "company_id",
        "facility_id",
        string="Facilities and services",
        help="What this shop offers. Shown on its microsite, grouped by "
        "subdivision. The section appears as soon as one item is ticked "
        "and stays hidden while none is.",
    )
    facility_block_title = fields.Char(
        string="Facilities section title",
        translate=True,
        help="Leave empty to use the default heading.",
    )
    facility_count = fields.Integer(compute="_compute_facility_count")

    def _compute_facility_count(self):
        for company in self:
            company.facility_count = len(company.facility_ids)

    def _facilities_by_category(self):
        """What this shop offers, grouped and ordered for the microsite.

        Returns a list of ``(category, facilities)`` rather than a dict so the
        template keeps the order the catalogue defines -- subdivision
        sequence, then item sequence, then name -- instead of whatever order
        the many-to-many happens to come back in. Archived items drop out on
        their own: unticking one in the catalogue has to remove it from every
        microsite at once, which is the reason the catalogue is shared in the
        first place.

        An empty list is also the whole visibility rule: the section renders
        ``t-if`` on this result, so a shop that has ticked nothing shows no
        section. There is no separate switch any more (client feedback,
        2026-09-15): a switch next to an empty list was a way to show a
        heading over nothing, and a way to tick things and see nothing.

        Sudo: rendered in public website context.
        """
        self.ensure_one()
        offered = self.sudo().facility_ids.filtered("active")
        grouped = []
        for category in offered.category_id.sorted(lambda c: (c.sequence, c.name)):
            items = offered.filtered(lambda item: item.category_id == category)
            grouped.append((category, items.sorted(lambda i: (i.sequence, i.name))))
        return grouped
