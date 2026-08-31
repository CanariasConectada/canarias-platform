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
        "subdivision.",
    )
    facility_block_title = fields.Char(
        string="Facilities block title",
        translate=True,
        help="Heading of the block on the microsite. Left empty it reads "
        "“Facilities and services”.",
    )
    facility_block_enabled = fields.Boolean(
        string="Show facilities on the website",
        default=True,
        help="Adds the block to this shop's site, above the footer. On by "
        "default: a new merchant company is born with the full corporate "
        "format, and the block is harmless while the shop has ticked no "
        "facility (it renders nothing). Existing shops were switched on by "
        "the 2026-08-17 migration; untick it to hide the block on a "
        "specific shop.",
    )
    facility_count = fields.Integer(compute="_compute_facility_count")

    def _compute_facility_count(self):
        for company in self:
            company.facility_count = len(company.facility_ids)

    def _facilities_by_category(self):
        """What this shop offers, grouped and ordered for the microsite.

        Returns a list of ``(category, facilities)`` rather than a dict so the
        template keeps the order the catalogue defines instead of whatever
        order the many-to-many happens to come back in. Archived items drop out
        on their own: unticking one in the catalogue has to remove it from
        every microsite at once, which is the reason the catalogue is shared in
        the first place.

        Sudo: rendered in public website context.
        """
        self.ensure_one()
        offered = self.sudo().facility_ids.filtered("active")
        grouped = []
        for category in offered.category_id.sorted(lambda c: (c.sequence, c.name)):
            items = offered.filtered(lambda item: item.category_id == category)
            grouped.append((category, items.sorted(lambda i: (i.sequence, i.name))))
        return grouped
