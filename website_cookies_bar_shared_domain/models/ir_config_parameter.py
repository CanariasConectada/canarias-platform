# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models
from odoo.exceptions import ValidationError

from .website import SHARED_DOMAIN_PARAM, normalize_shared_domain


class IrConfigParameter(models.Model):
    _inherit = "ir.config_parameter"

    @api.constrains("key", "value")
    def _check_cookies_bar_shared_domain(self):
        """Refuse a value the runtime would silently ignore.

        The runtime never trusts the stored value (it re-validates on every
        read, so a row written through SQL is harmless); this constraint only
        tells the administrator at once instead of leaving a dead setting.
        """
        for parameter in self:
            if parameter.key != SHARED_DOMAIN_PARAM or not parameter.value:
                continue
            if not normalize_shared_domain(parameter.value):
                raise ValidationError(
                    self.env._(
                        "The shared cookie consent domain must be a bare "
                        "registrable domain such as 'example.com': no scheme, "
                        "no path, no port, not an IP address, and never a "
                        "top-level or public suffix such as 'es' or 'co.uk'."
                    )
                )
