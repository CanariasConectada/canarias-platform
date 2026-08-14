# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class LocalContentTag(models.Model):
    """Transversal theme label attachable to any item.

    Brings back the legacy "tipo" (theme) level of the old modules as
    free tags: a tag may optionally be scoped to one content type for
    informative grouping, but its assignment to items is never
    restricted by type.
    """

    _name = "website.local.content.tag"
    _description = "Local Content Tag"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer(help="Color of the tag badges in the backend.")
    type_id = fields.Many2one(
        comodel_name="website.local.content.type",
        string="Content Type",
        ondelete="set null",
        help="Informative scoping only: a tag with a content type is "
        "meant for that vertical, an empty one is transversal. Items "
        "of any type may use any tag.",
    )
