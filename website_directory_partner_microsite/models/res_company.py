# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _get_directory_display_name(self):
        """The directory card carries the trade name, not the legal one.

        Reported in the navigation review backlog ("Correccion de nombres
        en directorio") and measured on 2026-09-02: 75 of 205 cards showed
        the legal name (Dayra Martinez Alonso) while the merchant's trade
        name (LA BELLE DOG) sat right next to it on microsite_name -- and
        the sync rewrote any hand fix back on its next pass, because the
        base module only knows the legal name.

        One deliberate exception: when several shops of the directory share
        one trade name (the three ANA MARGARITA ACADEMY branches, the two
        Astrid churrerias), the legal name stays -- it is what tells the
        branches apart on the card, and three identical entries would be
        worse than three formal ones.
        """
        self.ensure_one()
        trade_name = (self.microsite_name or "").strip()
        if not trade_name or trade_name == self.name:
            return super()._get_directory_display_name()
        # Compared in Python, not with =ilike: the trade name is data the
        # merchants type, and a % or _ in it would widen an SQL pattern.
        key = trade_name.casefold()
        twins = (
            self.sudo()
            .search(
                [
                    ("microsite_name", "!=", False),
                    ("show_in_directory", "=", True),
                    ("id", "!=", self.id),
                ]
            )
            .filtered(lambda c: (c.microsite_name or "").strip().casefold() == key)
        )
        if twins:
            return super()._get_directory_display_name()
        return trade_name
