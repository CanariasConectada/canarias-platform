# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .website import PARAM_ENABLED, PARAM_STATEMENT, PARAM_URL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    eu_emblem_enabled = fields.Boolean(
        string="Show the EU emblem",
        default=True,
        config_parameter=PARAM_ENABLED,
        help="Displays the European Union emblem next to the site logo, on "
        "every website of the platform.",
    )
    eu_emblem_statement = fields.Char(
        string="Funding statement",
        config_parameter=PARAM_STATEMENT,
        help="The exact wording your grant requires beside the emblem, e.g. "
        "“Financiado por la Unión Europea – NextGenerationEU”. The EU's "
        "visual identity rules normally require this mention: the emblem on "
        "its own is usually not enough. Left empty, only the flag is shown.",
    )
    eu_emblem_url = fields.Char(
        string="Funding statement link",
        config_parameter=PARAM_URL,
        help="Optional. Where the emblem links to — typically the page "
        "describing the grant.",
    )
