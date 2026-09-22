# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

# What a shop offers, added to the merchant's own page-content screen, and
# the heading over it. No visibility switch travels with them any more: the
# section shows exactly when something is ticked (2026-09-15).
FACILITY_FIELDS = ("facility_ids", "facility_block_title")


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
    facility_block_title = fields.Char(
        string="Section title",
        help="Leave empty to use the default heading.",
    )

    def _editable_field_names(self):
        return super()._editable_field_names() + list(FACILITY_FIELDS)
