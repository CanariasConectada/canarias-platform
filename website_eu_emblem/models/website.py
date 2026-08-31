# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models

# The statement is empty by default, and that is deliberate. The EU's own
# visual identity rules require the emblem to appear WITH the name of the fund
# that paid for the work ("Financiado por la Unión Europea – NextGenerationEU",
# "FEDER – Una manera de hacer Europa", …), and which one applies is a fact
# about the grant, not something this module may guess. Leaving it blank shows
# the emblem alone and lets whoever administers the grant fill in the exact
# wording from Settings, without a deploy.
PARAM_ENABLED = "website_eu_emblem.enabled"
PARAM_STATEMENT = "website_eu_emblem.statement"
PARAM_URL = "website_eu_emblem.url"

FALSEY = ("False", "false", "0", "")


class Website(models.Model):
    _inherit = "website"

    def _eu_emblem_values(self):
        """Everything the header template needs, in one read.

        A method rather than three lookups inside the template: the header
        renders on every page of 218 websites, and a template that reaches
        into ``ir.config_parameter`` itself is both slower to read and harder
        to test than one that receives a dict.
        """
        params = self.env["ir.config_parameter"].sudo()
        return {
            "enabled": params.get_param(PARAM_ENABLED, "True") not in FALSEY,
            "statement": params.get_param(PARAM_STATEMENT, "") or "",
            "url": params.get_param(PARAM_URL, "") or "",
        }
