# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from urllib.parse import quote_plus

from odoo import models

# Google Maps "embed" output needs no API key and is the same endpoint the
# merchant microsites have used since day one; every public page that shows
# a map goes through this helper so they all look and behave the same.
MAP_EMBED_URL = "https://maps.google.com/maps?q={query}&z={zoom}&ie=UTF8&output=embed"


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _canarias_map_embed_address(self):
        """Address text used as the map query, or ``""`` when empty.

        Field order and selection (street, city, zip; no street2) are the
        ones the microsites always used: the 218 existing sites must keep
        a byte-identical URL after moving to this helper.
        """
        self.ensure_one()
        address = " ".join(part for part in (self.street, self.city, self.zip) if part)
        return address.strip()

    def _canarias_map_embed_url(self, zoom=13):
        """Embeddable Google Maps URL for this partner's address.

        Returns ``False`` when there is no address text at all so QWeb
        callers can simply ``t-if`` on the result.
        """
        self.ensure_one()
        address = self._canarias_map_embed_address()
        if not address:
            return False
        return MAP_EMBED_URL.format(query=quote_plus(address), zoom=int(zoom))
