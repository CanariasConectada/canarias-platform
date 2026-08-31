# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

# What a shop offers, added to the merchant's own page-content screen. The
# block switch and its heading travel with it: deciding to show the block is
# part of the same sitting as deciding what goes in it.
FACILITY_FIELDS = ("facility_ids", "facility_block_enabled", "facility_block_title")


class MicrositeContentEditor(models.TransientModel):
    """Let the merchant tick their own facilities.

    The catalogue exists so a filter can read it, and the directory filter is
    only as good as what the 218 shops have actually ticked. Leaving that
    behind the company form -- which no merchant can open -- would have meant
    one person ticking boxes for everybody, forever.
    """

    _inherit = "microsite.content.editor"

    facility_ids = fields.Many2many(
        comodel_name="company.facility",
        string="What this shop offers",
    )
    facility_block_enabled = fields.Boolean(
        string="Show them on my page",
        help="Off by default. The ticks still feed the directory filter "
        "whether or not the block is shown.",
    )
    facility_block_title = fields.Char(string="Heading")

    def _editable_field_names(self):
        return super()._editable_field_names() + list(FACILITY_FIELDS)
