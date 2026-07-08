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
    directory_sync_pending = fields.Boolean(
        string="Directory Sync Pending",
        default=True,
        copy=False,
        help="Set when the company changed and its directory entry still has "
        "to be refreshed. A scheduled action syncs pending companies in the "
        "background, so the sync never blocks saving the company.",
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

        Returns the recordset of companies whose sync actually succeeded, so
        the caller only clears ``directory_sync_pending`` for those: a company
        whose savepoint rolled back stays pending and is retried next run.
        """
        synced = self.browse()
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
            else:
                synced |= company
        return synced

    def _sync_single_directory_entry(self):
        self.ensure_one()
        entry_model = (
            self.env["website.directory.entry"].sudo().with_context(active_test=False)
        )
        # A company owns at most one *active* directory entry (partial unique
        # index on company_id WHERE active). Operate ONLY on the canonical
        # entry -- the active one if any, else the oldest -- so a stale
        # archived duplicate never makes the write try to activate two rows at
        # once and violate that index (which would roll back the whole sync).
        entry = entry_model.search(
            [("company_id", "=", self.id)],
            order="active desc, id asc",
            limit=1,
        )
        values = self._prepare_directory_entry_values()
        if entry:
            # zone, is_published and short_description are deliberately NOT
            # rewritten on update: they may have been curated by hand.
            entry.write(values)
        else:
            values.update(
                company_id=self.id,
                zone=self._get_directory_zone(),
                is_published=True,
            )
            entry_model.create(values)

    # ------------------------------------------------------------------
    # Async sync: cron drains the companies flagged as pending
    # ------------------------------------------------------------------
    @api.model
    def _cron_sync_directory_entries(self, batch_size=200):
        """Sync the directory entry of every company flagged as pending.

        Runs in the background (``ir.cron``) so saving a company never waits
        for the directory sync. Companies are flagged on create/write and
        drained here in batches; if a full batch is processed the cron
        re-triggers itself to keep going without waiting a full interval.
        """
        companies = self.with_context(active_test=False).search(
            [("directory_sync_pending", "=", True)], limit=batch_size
        )
        if not companies:
            return
        synced = companies._sync_to_directory_entry()
        # Only clear the flag for companies that actually synced. Ones whose
        # savepoint failed stay pending and are retried on the next run.
        synced.directory_sync_pending = False
        # Re-trigger to drain the next batch only while we keep making
        # progress; if a whole batch failed, wait for the next scheduled run
        # instead of hot-looping on the same broken records.
        if len(companies) == batch_size and synced:
            cron = self.env.ref(
                "website_directory.cron_sync_directory_entries",
                raise_if_not_found=False,
            )
            if cron:
                cron._trigger()

    # ------------------------------------------------------------------
    # ORM overrides — flag pending instead of syncing inline
    # ------------------------------------------------------------------
    def write(self, vals):
        # Archiving a company always removes it from the directory.
        if "active" in vals and not vals["active"]:
            vals = dict(vals, show_in_directory=False)
        res = super().write(vals)
        trigger_fields = self._get_directory_sync_fields() | PARTNER_SYNC_FIELDS
        # ``directory_sync_pending`` is not a trigger field, so flagging here
        # never recurses back into this branch.
        if trigger_fields.intersection(vals):
            self.filtered(lambda c: not c.directory_sync_pending).write(
                {"directory_sync_pending": True}
            )
        return res
