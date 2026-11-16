# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models


class ResCompany(models.Model):
    _inherit = "res.company"

    def _get_microsite_title_fallback(self):
        """Trade name (``comercial``, from ``res_company_zone``) before the
        legal name the base module falls back to."""
        self.ensure_one()
        return (self.comercial or "").strip() or super()._get_microsite_title_fallback()

    # Only here to attach the dependency: the chain itself lives in the hook
    # above, and @api.depends cannot be declared on a hook.
    @api.depends("comercial")
    def _compute_microsite_title(self):
        super()._compute_microsite_title()

    def _get_directory_sync_fields(self):
        """A new cover title must reach the directory card (see
        `_get_directory_display_name`); the partner-side trigger for
        ``comercial`` lives in ``res_partner.py``."""
        return super()._get_directory_sync_fields() | {"microsite_name"}

    def _get_directory_display_name(self):
        """The directory card shows the resolved cover title
        (``microsite_title``), not the legal name.

        Shops resolving to one and the same title keep their legal name, so
        branches of one brand stay distinguishable on the directory.
        """
        self.ensure_one()
        title = (self.microsite_title or "").strip()
        if not title or title == self.name:
            return super()._get_directory_display_name()
        # Compared in Python, not with =ilike: the title is data the merchants
        # type, a % or _ in it would widen an SQL pattern, and the resolved
        # title is not a stored column anyway. Accepted cost: one search per
        # card over the ~212 directory companies, read from cache after the
        # first card of a 200-company sync batch. Explicit `active` leaf: the
        # cron runs with active_test=False and an archived legacy company
        # must not count as a twin.
        key = title.casefold()
        twins = (
            self.sudo()
            .search(
                [
                    ("show_in_directory", "=", True),
                    ("active", "=", True),
                    ("id", "!=", self.id),
                ]
            )
            .filtered(lambda c: (c.microsite_title or "").strip().casefold() == key)
        )
        if twins:
            return super()._get_directory_display_name()
        return title
