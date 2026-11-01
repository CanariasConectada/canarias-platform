# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CompanyFacilityCategory(models.Model):
    """A subdivision of the facilities block: Accessibility, Payment, Parking…

    Asked for on 2026-08-16, together with the renaming of the block to
    "Instalaciones y servicios": what a shop offers is a list of thirty small
    things, and thirty icons in a row is a wall. Grouped under four headings it
    is something a visitor can read in three seconds.

    The catalogue is a table rather than a selection field for the same reason
    the engines are: the client is meant to extend it themselves, and adding a
    subdivision must never mean a migration.
    """

    _name = "company.facility.category"
    _description = "Company Facility Category"
    _inherit = ["auto.translate.mixin"]
    _order = "sequence, name, id"

    name = fields.Char(required=True, translate=True)
    icon = fields.Char(
        default="fa-th-large",
        help="Font Awesome class shown beside the heading, e.g. fa-wheelchair.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    facility_ids = fields.One2many("company.facility", "category_id")
    facility_count = fields.Integer(compute="_compute_facility_count")

    _name_unique = models.Constraint(
        "UNIQUE (name)", "There is already a subdivision with that name."
    )

    def _compute_facility_count(self):
        counts = dict(
            self.env["company.facility"]._read_group(
                domain=[("category_id", "in", self.ids)],
                groupby=["category_id"],
                aggregates=["__count"],
            )
        )
        for category in self:
            category.facility_count = counts.get(category, 0)

    def _auto_translate_fields(self):
        return ["name"]
