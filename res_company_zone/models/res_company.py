# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from odoo.addons.website_directory.models.website_directory_entry import (
    ZONE_ALIASES,
    ZONE_SELECTION,
)


class ResCompany(models.Model):
    _inherit = "res.company"

    # Same selection as the directory entry, on purpose: the entry field is
    # what the public filter reads, and two lists that can drift apart would
    # silently drop a zone from the filter.
    commercial_zone = fields.Selection(
        selection=ZONE_SELECTION,
        string="Zona comercial",
        default="canarias",
        required=True,
        index=True,
        help="Neighbourhood this business belongs to. Drives the zone filter "
        "of the public directory and the catalogue of the zone shops.",
    )

    def _get_directory_zone(self):
        """Zone written onto this company's directory entry.

        ``website_directory`` left this as an extension hook returning the
        global zone, explicitly waiting for a zone module — this is it.
        """
        self.ensure_one()
        return self.commercial_zone or "canarias"

    def _get_directory_sync_fields(self):
        """Editing the zone must re-sync the directory entry.

        Without this the field would change on the company form and the
        public directory would keep filtering by the old value until
        something else happened to touch the record.
        """
        return super()._get_directory_sync_fields() | {"commercial_zone"}

    def write(self, vals):
        """Keep existing directory entries aligned with the company zone.

        The base sync only sets the zone when an entry is *created* (see
        ``_get_directory_zone``'s docstring), which is right for a field a
        human may have adjusted by hand — but the company form is where the
        zone is meant to be edited, so a change here has to win.
        """
        res = super().write(vals)
        if "commercial_zone" in vals:
            entries = (
                self.env["website.directory.entry"]
                .sudo()
                .with_context(active_test=False)
                .search([("company_id", "in", self.ids)])
            )
            for entry in entries:
                zone = entry.company_id._get_directory_zone()
                if entry.zone != zone:
                    entry.zone = zone
        return res

    @classmethod
    def _normalise_zone(cls, raw):
        """Map a legacy spelling onto one of the selection values.

        The old database stored ``lomo_los_frailes`` and ``lomo los frailes``
        alongside the canonical key, which is why ``website_directory`` had to
        carry ``ZONE_ALIASES`` in the first place.
        """
        value = (raw or "").strip().lower()
        if not value:
            return "canarias"
        for canonical, aliases in ZONE_ALIASES.items():
            if value in aliases:
                return canonical
        known = {key for key, _label in ZONE_SELECTION}
        return value if value in known else "canarias"
