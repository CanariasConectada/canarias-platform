# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class LocalContentCategory(models.Model):
    """First taxonomy level of a content type."""

    _name = "website.local.content.category"
    _description = "Local Content Category"
    _order = "type_id, sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    type_id = fields.Many2one(
        comodel_name="website.local.content.type",
        string="Content Type",
        required=True,
        index=True,
        ondelete="restrict",
    )
    subcategory_ids = fields.One2many(
        comodel_name="website.local.content.subcategory",
        inverse_name="category_id",
        string="Subcategories",
    )
    subcategory_count = fields.Integer(compute="_compute_subcategory_count")

    def _compute_subcategory_count(self):
        for record in self:
            record.subcategory_count = len(record.subcategory_ids)
