# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class CompanyFacility(models.Model):
    """One thing a shop offers: step-free access, card payment, home delivery.

    Kept apart from the shop that offers it -- a many-to-many rather than a
    line per company -- so that renaming "Wifi gratis" or giving it a better
    icon happens once and reaches all 216 microsites, and so that the same
    wording is translated once instead of 216 times.
    """

    _name = "company.facility"
    _description = "Company Facility"
    _inherit = ["auto.translate.mixin"]
    _order = "category_id, sequence, name, id"

    name = fields.Char(required=True, translate=True)
    category_id = fields.Many2one(
        "company.facility.category",
        string="Subdivision",
        required=True,
        ondelete="restrict",
        index=True,
    )
    icon = fields.Char(
        default="fa-check",
        help="Font Awesome class shown beside the item, e.g. fa-wifi.",
    )
    description = fields.Char(
        translate=True,
        help="One short line under the name. Leave it empty when the name says "
        "everything.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    company_ids = fields.Many2many(
        "res.company",
        "res_company_facility_rel",
        "facility_id",
        "company_id",
        string="Offered by",
    )

    _name_unique_per_category = models.Constraint(
        "UNIQUE (category_id, name)",
        "That subdivision already has an item with that name.",
    )

    def _auto_translate_fields(self):
        return ["name", "description"]
