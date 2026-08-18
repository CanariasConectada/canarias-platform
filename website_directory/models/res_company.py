# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

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

        Priority: extension hook > company website domain > partner website.
        The company's own microsite outranks whatever external site the
        merchant typed on their contact card: the directory exists to send
        visitors INTO the platform, and the microsite links back to the
        external site anyway.
        """
        self.ensure_one()
        url = self._get_directory_extra_website_url()
        if not url and self.website_id.domain:
            url = self.website_id.domain
        if not url:
            url = self.partner_id.website or ""
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
            # website_url is NOT written: it is a non-stored computed field
            # on the entry that reads _get_directory_website_url() live.
            "active": self.show_in_directory,
        }
        # The 2026 logo recovery restored merchant logos onto website.logo;
        # most companies never got one of their own, so the card falls back
        # to the site's logo rather than showing a placeholder.
        if self.logo:
            values["image_1920"] = self.logo
        elif self.website_id.logo:
            values["image_1920"] = self.website_id.logo
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
    # Merchant self-service: set your own category
    # ------------------------------------------------------------------
    def _get_own_company_for_directory(self):
        """The company the current user may edit, or an empty recordset.

        A merchant here is a portal user (``share=True``) with no backend, and
        their link to a business is ``res.users.company_id``. That is the
        single source of truth for "their own company": not the partner, and
        not the allowed-companies list, which a portal user does not really
        control.

        Returns empty instead of raising so a caller can render "you have no
        shop" rather than an error page.
        """
        user = self.env.user
        if not user or user._is_public():
            return self.browse()
        company = user.company_id
        if not company or not company.active:
            return self.browse()
        # The platform's own company is nobody's shop. Letting whoever holds a
        # portal account on it recategorise Canarias Conectada would be a
        # privilege escalation dressed up as a form field.
        main = self.env.ref("base.main_company", raise_if_not_found=False)
        if main and company == main:
            return self.browse()
        return company.sudo()

    def set_own_directory_category(self, category_id):
        """Set the directory category of the CALLER's own company.

        Writing ``category_id`` on ``res.company`` needs Administration
        rights — a merchant gets ``AccessError: No puede modificar
        'Compañías'``. Handing a portal user those rights so they can fix a
        dropdown would be absurd, so the write is escalated here instead. The
        escalation is worth exactly as much as the checks around it:

        * the company is resolved from the SESSION, never from the request, so
          no id sent from outside can aim this at somebody else's shop;
        * only ``category_id`` is written, never a second field;
        * the category has to exist, be active and be assignable.

        ``self`` is deliberately ignored: the caller does not get to choose
        the company. That is the entire point of the method.

        Every rejection is a ``UserError`` (or ``AccessError``) on purpose:
        those are the only exceptions the controller catches to redirect with
        ``?error=1``. Anything else escapes as a 500. The checks live HERE and
        not only in the controller because this is a public ORM method: it is
        also reachable over XML-RPC, where there is no controller at all.
        """
        company = self._get_own_company_for_directory()
        if not company:
            raise AccessError(
                _(
                    "Your user is not linked to a business, so there is no "
                    "category to set."
                )
            )

        if not category_id:
            company.category_id = False
            return company

        # ``category_id`` arrives straight from a form field, so it can be
        # anything: "abc", "1.5", "  ". A bare ``int()`` raises ValueError,
        # which nobody catches, so a typo in a POST became a 500 instead of
        # the "we could not save it" page. Non-integer numbers are rejected
        # too instead of being truncated: ``int(1.5)`` would silently write a
        # DIFFERENT category than the one asked for.
        try:
            category_id = int(str(category_id).strip())
        except (TypeError, ValueError) as exc:
            raise UserError(_("That category does not exist.")) from exc

        category = self.env["res.company.category"].sudo().browse(category_id).exists()
        if not category or not category.active:
            raise UserError(_("That category does not exist."))

        # A "view" category is a folder that only groups other categories:
        # ``res.company.category_id`` is declared with
        # ``domain=[("type", "=", "normal")]``, but a domain is a UI hint that
        # nothing enforces on write. Assigning a folder also corrupts
        # ``company_qty``, which counts companies on normal categories and
        # only sums its children on view ones — the company would be counted
        # nowhere on the public directory.
        if category.type != "normal":
            raise UserError(
                _(
                    "That category only groups other categories. "
                    "Choose one of its subcategories."
                )
            )

        company.category_id = category.id
        return company

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
