# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class CertificationHighlight(models.Model):
    """What a seal means, as a fixed icon list owned by the vertical.

    ``certification.positive.item`` already answers "what did THIS shop score
    well on", but it can only answer it for a shop whose seal came from an
    evaluation. Seals imported from the previous platform carry no
    ``user_input_id`` at all, so that list is empty for them and their
    microsite shows a seal with nothing explaining it.

    These highlights are the fallback: curated per vertical, identical for
    every holder of the seal, and therefore available the moment a company is
    certified — including for imported seals and for a vertical whose
    questionnaire has not been filled in yet.
    """

    _name = "certification.highlight"
    _description = "Certification Highlight"
    _order = "sequence, id"

    type_id = fields.Many2one(
        "certification.type",
        required=True,
        ondelete="cascade",
        index=True,
    )
    label = fields.Char(required=True, translate=True)
    description = fields.Char(
        translate=True,
        help="Optional second line, shown smaller under the label.",
    )
    icon = fields.Char(
        default="fa-check-circle",
        required=True,
        help="Font Awesome class shown next to the label, e.g. fa-wheelchair.",
    )
    sequence = fields.Integer(default=10)
