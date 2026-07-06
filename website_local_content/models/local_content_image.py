# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class LocalContentImage(models.Model):
    """Additional photograph of an item (public gallery)."""

    _name = "website.local.content.image"
    _description = "Local Content Item Image"
    _inherit = ["image.mixin"]
    _order = "sequence, id"

    name = fields.Char(string="Caption")
    sequence = fields.Integer(default=10)
    item_id = fields.Many2one(
        comodel_name="website.local.content.item",
        string="Item",
        required=True,
        index=True,
        ondelete="cascade",
    )
