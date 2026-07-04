# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

# Partner-related keys that Odoo forwards from the company form and that
# must refresh the directory entry when written on the company.
PARTNER_SYNC_FIELDS = {"phone", "email", "street", "city", "vat", "website"}


class ResCompany(models.Model):
    _inherit = "res.company"

    show_in_directory = fields.Boolean(
        string="Show in Directory",
        default=True,
        help="If set, this company is listed in the public website directory.",
    )

    # ------------------------------------------------------------------
    # Extension hooks (override in zone / microsite modules)
    # ------------------------------------------------------------------
    def _get_directory_zone(self):
        """Zone assigned to a NEW directory entry of this company.

        The base module knows nothing about zones: it always returns the
        global zone. The future zone module must override this method to
        map its own data to the entry ``zone`` selection. Existing entries
        keep their zone: the sync only sets it on creation.
        """
        self.ensure_one()
        return "canarias"

    def _get_directory_extra_website_url(self):
        """Preferred public URL provided by extension modules.

        The base module only knows base + website fields. Microsite modules
        (custom domains, subdomains, main website...) must override this
        method and return their computed URL, or empty to fall back to the
        base priorities of :meth:`_get_directory_website_url`.
        """
        self.ensure_one()
        return ""

    def _get_directory_sync_fields(self):
        """Company fields that trigger a directory sync when written.

        Extension modules append their own fields here (e.g. the zone
        module adds its zone field, microsite modules their domain fields).
        """
        return {"name", "logo", "show_in_directory", "website_id", "active"}

    # ------------------------------------------------------------------
    # Sync company -> directory entry
    # ------------------------------------------------------------------
    def _get_directory_website_url(self):
        """Public URL of the company for the directory entry.

        Priority: extension hook > partner website > company website domain.
        """
        self.ensure_one()
        url = self._get_directory_extra_website_url()
        if not url:
            url = self.partner_id.website or ""
        if not url and self.website_id.domain:
            url = self.website_id.domain
        if url and not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    def _prepare_directory_entry_values(self):
        """Values written on the directory entry at every sync."""
        self.ensure_one()
        partner = self.partner_id
        values = {
            "name": self.name,
            "phone": partner.phone or "",
            "email": partner.email or "",
            "street": partner.street or "",
            "city": partner.city or "",
            "vat": partner.vat or "",
            "website_url": self._get_directory_website_url(),
            "active": self.show_in_directory,
        }
        if self.logo:
            values["image_1920"] = self.logo
        return values

    def _sync_to_directory_entry(self):
        """Create or update the directory entry of each company.

        Each company is synced inside its own savepoint so a failure never
        breaks the company write itself, but it is ALWAYS logged.
        """
        for company in self:
            try:
                with self.env.cr.savepoint():
                    company._sync_single_directory_entry()
            except Exception:
                _logger.warning(
                    "Directory sync failed for company %r (id %s)",
                    company.name,
                    company.id,
                    exc_info=True,
                )

    def _sync_single_directory_entry(self):
        self.ensure_one()
        entry_model = (
            self.env["website.directory.entry"].sudo().with_context(active_test=False)
        )
        entries = entry_model.search([("company_id", "=", self.id)])
        values = self._prepare_directory_entry_values()
        if entries:
            # zone, is_published and short_description are deliberately NOT
            # rewritten on update: they may have been curated by hand.
            entries.write(values)
        else:
            values.update(
                company_id=self.id,
                zone=self._get_directory_zone(),
                is_published=True,
            )
            entry_model.create(values)

    def action_sync_to_directory(self):
        """Form button: force a manual sync of the directory entry."""
        self._sync_to_directory_entry()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": self.env._("Directory synchronized"),
                "message": self.env._(
                    "The company has been synchronized with its "
                    "website directory entry."
                ),
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # ORM overrides
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        # Extend the allowed companies so the sync can read the new records
        # even in restricted multi-company environments.
        allowed_ids = list(
            self.env.context.get("allowed_company_ids") or [self.env.company.id]
        )
        new_ids = [c.id for c in companies if c.id not in allowed_ids]
        companies.with_context(
            allowed_company_ids=allowed_ids + new_ids
        )._sync_to_directory_entry()
        return companies

    def write(self, vals):
        # Archiving a company always removes it from the directory.
        if "active" in vals and not vals["active"]:
            vals = dict(vals, show_in_directory=False)
        res = super().write(vals)
        trigger_fields = self._get_directory_sync_fields() | PARTNER_SYNC_FIELDS
        if trigger_fields.intersection(vals):
            self._sync_to_directory_entry()
        return res
