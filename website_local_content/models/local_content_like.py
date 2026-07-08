# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class LocalContentLike(models.Model):
    """Anonymous like on an item.

    Faithful to the legacy model: visitors are identified by a random
    session key stored in a long-lived cookie (no login required), with
    the client IP kept for abuse review. One like per session and item.
    """

    _name = "website.local.content.like"
    _description = "Local Content Like"
    _order = "create_date desc"

    item_id = fields.Many2one(
        comodel_name="website.local.content.item",
        string="Item",
        required=True,
        index=True,
        ondelete="cascade",
    )
    session_key = fields.Char(
        required=True,
        index=True,
        help="Random anonymous visitor key stored in the browser cookie.",
    )
    ip_address = fields.Char(help="Client IP, kept only for abuse review.")

    _item_session_uniq = models.Constraint(
        "unique(item_id, session_key)",
        "This visitor already liked this item.",
    )
