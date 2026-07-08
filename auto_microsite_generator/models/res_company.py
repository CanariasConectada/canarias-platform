# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from odoo import _, api, models

_logger = logging.getLogger(__name__)

# External IDs created by the data migration are anchored to this module
# (see docs/plan-maestro-migracion.md, section 3). Any website content
# (pages, views, menus) carrying such an external ID was brought in "as is"
# by the migration and must NEVER be regenerated or overwritten.
MIGRATION_XMLID_MODULE = "canarias_mig"

# System parameter (Settings > Technical > Parameters) that turns the whole
# automatism on or off without uninstalling the module. Defaults to enabled.
ENABLE_PARAM = "auto_microsite_generator.enabled"

# Optional domain suffix used to build a default website domain from the
# company name, e.g. ".canariasconectada.es" -> https://bakery.canariasconectada.es
# Empty by default: the data migration owns real domains (it only "casa
# dominios" afterwards), and empty domains keep test routing unambiguous.
DOMAIN_SUFFIX_PARAM = "auto_microsite_generator.domain_suffix"

# Structural / umbrella company names that must not receive a microsite.
PROTECTED_NAME_PATTERNS = (
    "zona comercial",
    "canarias conectada",
    "my company",
)


def _normalize_subdomain(name):
    """Return a DNS-safe subdomain built from a company name."""
    subdomain = re.sub(r"[^a-z0-9\s]", "", (name or "").lower())
    subdomain = re.sub(r"\s+", "", subdomain)[:30]
    return subdomain or "empresa"


class ResCompany(models.Model):
    _inherit = "res.company"

    # ------------------------------------------------------------------
    # Company creation hook
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        if not self._auto_microsite_is_enabled():
            return companies
        # Record rules would hide the brand-new companies (they are not in
        # allowed_company_ids yet) while we build their websites, so widen the
        # context for the generation pass only.
        allowed = list(
            self.env.context.get("allowed_company_ids") or self.env.companies.ids
        )
        new_ids = [company.id for company in companies if company.id not in allowed]
        generation = companies
        if new_ids:
            generation = companies.with_context(allowed_company_ids=allowed + new_ids)
        for company in generation:
            company._auto_generate_microsite()
        return companies

    # ------------------------------------------------------------------
    # Public entry point (also callable from a data migration or shell)
    # ------------------------------------------------------------------
    def _auto_generate_microsite(self):
        """Provision website + homepage + menu for this company.

        Idempotent and non-destructive: it only creates what is missing and
        never overwrites content anchored to the data migration.
        """
        self.ensure_one()
        if self._microsite_is_protected():
            _logger.info(
                "Skipping auto-microsite for protected company %s.",
                self.display_name,
            )
            return
        website = self._get_or_create_microsite_website()
        if not website:
            return
        migrated = self._microsite_has_migrated_content(website)
        self._ensure_microsite_menu(website, skip=migrated)
        self._ensure_microsite_homepage(website)

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    def _auto_microsite_is_enabled(self):
        """False when disabled by context flag or system parameter."""
        if self.env.context.get("no_microsite_auto"):
            return False
        value = self.env["ir.config_parameter"].sudo().get_param(ENABLE_PARAM, "True")
        return str(value).strip().lower() not in ("false", "0", "")

    def _microsite_is_protected(self):
        self.ensure_one()
        name = (self.name or "").lower()
        return any(pattern in name for pattern in PROTECTED_NAME_PATTERNS)

    def _is_migrated_record(self, record):
        """True when ``record`` carries a ``canarias_mig.*`` external ID."""
        if not record:
            return False
        return bool(
            self.env["ir.model.data"]
            .sudo()
            .search_count(
                [
                    ("module", "=", MIGRATION_XMLID_MODULE),
                    ("model", "=", record._name),
                    ("res_id", "=", record.id),
                ]
            )
        )

    def _microsite_has_migrated_content(self, website):
        """True when any page/view/menu of ``website`` came from the migration.

        Used to leave migrated navigation untouched. The homepage itself is
        guarded independently by :meth:`_ensure_microsite_homepage`.
        """
        self.ensure_one()
        pages = (
            self.env["website.page"].sudo().search([("website_id", "=", website.id)])
        )
        views = self.env["ir.ui.view"].sudo().search([("website_id", "=", website.id)])
        menus = (
            self.env["website.menu"].sudo().search([("website_id", "=", website.id)])
        )
        domain = [
            ("module", "=", MIGRATION_XMLID_MODULE),
            "|",
            "|",
            "&",
            ("model", "=", "website.page"),
            ("res_id", "in", pages.ids),
            "&",
            ("model", "=", "ir.ui.view"),
            ("res_id", "in", views.ids),
            "&",
            ("model", "=", "website.menu"),
            ("res_id", "in", menus.ids),
        ]
        return bool(self.env["ir.model.data"].sudo().search_count(domain))

    # ------------------------------------------------------------------
    # Website
    # ------------------------------------------------------------------
    def _get_or_create_microsite_website(self):
        self.ensure_one()
        if self.website_id:
            return self.website_id
        values = {"name": self.name, "company_id": self.id}
        domain = self._microsite_default_domain()
        if domain:
            values["domain"] = domain
        website = self.env["website"].sudo().create(values)
        # res.company.website_id is a stored compute keyed on website.company_id;
        # website.create() already recomputes it, but refresh to be explicit.
        self.invalidate_recordset(["website_id"])
        return website

    def _microsite_default_domain(self):
        self.ensure_one()
        suffix = (
            self.env["ir.config_parameter"].sudo().get_param(DOMAIN_SUFFIX_PARAM, "")
        )
        if not suffix:
            return ""
        return f"https://{_normalize_subdomain(self.name)}{suffix}"

    # ------------------------------------------------------------------
    # Menu (create-only, never destructive)
    # ------------------------------------------------------------------
    def _ensure_microsite_menu(self, website, skip=False):
        """Ensure the standard top-menu entries exist on ``website``.

        Create-only by design: existing menus are never renamed or removed,
        so migrated navigation and manual edits survive. When the website
        already carries migrated menus the whole step is skipped.
        """
        self.ensure_one()
        if skip:
            _logger.info(
                "Microsite %s has migrated menus; leaving them untouched.",
                website.name,
            )
            return
        Menu = self.env["website.menu"].sudo()
        root = Menu.search(
            [("website_id", "=", website.id), ("parent_id", "=", False)],
            limit=1,
        )
        if not root:
            root = Menu.create({"name": self.name, "website_id": website.id})
        items = [
            (_("Home"), "/", 10),
            (_("Shop"), "/shop", 20),
            (_("Directory"), "/comercio", 30),
        ]
        for label, url, sequence in items:
            exists = Menu.search(
                [
                    ("website_id", "=", website.id),
                    ("parent_id", "=", root.id),
                    ("url", "=", url),
                ],
                limit=1,
            )
            if not exists:
                Menu.create(
                    {
                        "name": label,
                        "url": url,
                        "parent_id": root.id,
                        "website_id": website.id,
                        "sequence": sequence,
                    }
                )

    # ------------------------------------------------------------------
    # Homepage
    # ------------------------------------------------------------------
    def _get_microsite_homepage_arch(self):
        """Thin homepage wrapper calling the shared microsite content template."""
        self.ensure_one()
        return (
            f'<t name="Homepage" t-name="auto_microsite_generator.homepage_{self.id}">\n'
            '    <t t-call="website.layout">\n'
            '        <div id="wrap" class="oe_structure">\n'
            "            <t t-call="
            '"auto_microsite_generator.default_homepage_content"/>\n'
            "        </div>\n"
            "    </t>\n"
            "</t>\n"
        )

    def _ensure_microsite_homepage(self, website):
        """Install the default microsite homepage at ``/`` unless migrated.

        ``website.create`` bootstraps a blank ``/`` page, which we replace with
        the microsite welcome content. If that ``/`` page (or its view) was
        brought by the migration, it is left exactly as is.
        """
        self.ensure_one()
        Page = self.env["website.page"].sudo()
        View = self.env["ir.ui.view"].sudo()
        page = Page.search(
            [("website_id", "=", website.id), ("url", "=", "/")], limit=1
        )
        if page and (
            self._is_migrated_record(page) or self._is_migrated_record(page.view_id)
        ):
            _logger.info(
                "Microsite %s: kept migrated homepage untouched.", website.name
            )
            return page
        arch = self._get_microsite_homepage_arch()
        view_key = f"auto_microsite_generator.homepage_{self.id}"
        if page:
            page.view_id.write({"arch_db": arch, "key": view_key})
            page.is_published = True
            return page
        view = View.create(
            {
                "name": f"Microsite Homepage - {self.name}",
                "type": "qweb",
                "key": view_key,
                "arch_db": arch,
                "website_id": website.id,
            }
        )
        return Page.create(
            {
                "name": f"Microsite Homepage - {self.name}",
                "url": "/",
                "view_id": view.id,
                "website_id": website.id,
                "is_published": True,
            }
        )
