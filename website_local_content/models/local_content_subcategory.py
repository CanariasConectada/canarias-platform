# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class LocalContentSubcategory(models.Model):
    """Second taxonomy level, always attached to a category."""

    _name = "website.local.content.subcategory"
    _description = "Local Content Subcategory"
    _order = "category_id, sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    category_id = fields.Many2one(
        comodel_name="website.local.content.category",
        string="Category",
        required=True,
        index=True,
        ondelete="restrict",
    )
    type_id = fields.Many2one(
        related="category_id.type_id",
        store=True,
        string="Content Type",
    )
