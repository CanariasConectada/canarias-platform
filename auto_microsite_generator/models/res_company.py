# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# External IDs created by the data migration are anchored to this module
# (see docs/plan-maestro-migracion.md, section 3). Any website content
# (pages, views, menus) carrying such an external ID was brought in "as is"
# by the migration and must NEVER be regenerated or overwritten.
MIGRATION_XMLID_MODULE = "canarias_mig"

# System parameter (Settings > Technical > Parameters) that turns the whole
# automatism on or off without uninstalling the module. Defaults to enabled.
ENABLE_PARAM = "auto_microsite_generator.enabled"

# Domain suffix used to build a default website domain from the company
# name, e.g. ".canariasconectada.es" -> https://bakery.canariasconectada.es
# Seeded by data/ir_config_parameter.xml (noupdate) to the production
# convention, so a newly created microsite is born routable. When the
# parameter is emptied on purpose the website is created without a domain
# and a warning is logged (see _microsite_default_domain).
DOMAIN_SUFFIX_PARAM = "auto_microsite_generator.domain_suffix"

# How a brand-new company gets the subdomain its microsite lives on.
#
#   "ask"  -- nobody guesses it. The website is NOT provisioned when the
#             company is created; the company form shows "Create microsite",
#             which asks for the subdomain and hands back the exact hostname
#             to point at the server. This is the default because DNS here is
#             manual (there is no registrar API, and the wildcard is renewed
#             by hand), so a site born on a hostname nobody registered is a
#             dead link with a merchant attached to it.
#   "auto" -- the historical behaviour: the subdomain is derived from the
#             company name. Kept for bulk imports and for fixtures, where
#             answering a question 200 times is not an option.
#
# A subdomain passed explicitly to ``create`` always provisions the site,
# whatever the mode says: the caller has already answered the question.
SUBDOMAIN_MODE_PARAM = "auto_microsite_generator.subdomain_mode"
SUBDOMAIN_MODE_ASK = "ask"
SUBDOMAIN_MODE_AUTO = "auto"

# One DNS label: letters, digits and inner hyphens, 63 characters at most.
# Deliberately stricter than DNS itself (no uppercase, no leading digit rule
# bending) so what the operator types is exactly what ends up in the zone
# file and in the certificate.
SUBDOMAIN_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

# Wording of the three standard menu entries in every language the estate
# publishes, taken verbatim from the live microsites (website 217).
#
# They are seeded on creation instead of being left to the machine
# translator for one blunt reason: "Comercio" out of context is not the
# directory, it is the noun, and every engine we tried returns
# Trade/Handel/Commerce -- which is what website 221 shipped with. Seeding
# also protects them for good: website_auto_translate refuses to overwrite a
# language that already holds something other than the source string
# (``_may_overwrite``), so no coupling between the two modules is needed.
MENU_LABELS = {
    "/": {
        "es_ES": "Inicio",
        "en_US": "Home",
        "de_DE": "Home",
        "fr_FR": "Accueil",
        "it_IT": "Home",
        "pl_PL": "Strona główna",
        "pt_PT": "Início",
    },
    "/shop": {
        "es_ES": "Tienda",
        "en_US": "Shop",
        "de_DE": "Shop",
        "fr_FR": "Boutique",
        "it_IT": "Negozio",
        "pl_PL": "Sklep",
        "pt_PT": "Loja",
    },
    "/comercio": {
        "es_ES": "Comercio",
        "en_US": "Directory",
        "de_DE": "Verzeichnis",
        "fr_FR": "Annuaire",
        "it_IT": "Elenco",
        "pl_PL": "Katalog",
        "pt_PT": "Diretório",
    },
    "/explora/lugares-de-interes": {
        "es_ES": "Lugares de Interés",
        "en_US": "Places of Interest",
        "de_DE": "Sehenswürdigkeiten",
        "fr_FR": "Lieux d'intérêt",
        "it_IT": "Luoghi di interesse",
        "pl_PL": "Atrakcje",
        "pt_PT": "Locais de interesse",
    },
    # Absolute on purpose: the reviews page answers on the portal alone
    # (404 on every zone and merchant site), so the entry deep-links there
    # the same way the zone dropdown deep-links the zone shops.
    "https://canariasconectada.es/resenas": {
        "es_ES": "Reseñas",
        "en_US": "Reviews",
        "de_DE": "Bewertungen",
        "fr_FR": "Avis",
        "it_IT": "Recensioni",
        "pl_PL": "Opinie",
        "pt_PT": "Avaliações",
    },
}

# "Zonas Comerciales" dropdown created on every new microsite: the
# navigation that ties the network together (from any merchant's website a
# visitor can jump to the other zones). Labels and URLs mirror the
# production menus restored by the one-off fix f18_zone_menu_restore; the
# zone names are proper nouns and the two Spanish labels are the production
# wording, so none of them go through translation.
ZONE_MENU_NAME = "Zonas Comerciales"
ZONE_MENU_SEQUENCE = 40
ZONE_MENU_CHILDREN = (
    ("Todas", "https://canariasconectada.es", 10),
    ("Guanarteme", "https://guanarteme.canariasconectada.es", 20),
    ("Lomo Los Frailes", "https://lomolosfrailes.canariasconectada.es", 30),
    ("Tamaraceite", "https://tamaraceite.canariasconectada.es", 40),
)
# Presence is decided on this url, not on the parent's label: a dropdown
# somebody renamed still has the links and must be left alone (same probe
# as f18_zone_menu_restore).
ZONE_MENU_PROBE_URL = ZONE_MENU_CHILDREN[1][1]

# "Guía Local" dropdown: the platform's own verticals. Measured on
# 2026-09-02 (and first raised in the navigation review of 2026-08-02):
# Memoria Viva, Lugares de Interés and Reseñas exist and answer 200, yet
# 215 of 218 sites linked none of them -- the portal included. The zone
# sites carry this dropdown already (Guía Local, menus 118/130/142); this
# makes it part of what a microsite is born with. Memoria Viva is a proper
# noun and keeps its name in every language; the other two translate
# through MENU_LABELS.
LOCAL_GUIDE_MENU_NAME = "Guía Local"
LOCAL_GUIDE_MENU_LABELS = {
    "es_ES": "Guía Local",
    "en_US": "Local Guide",
    "de_DE": "Lokaler Guide",
    "fr_FR": "Guide local",
    "it_IT": "Guida locale",
    "pl_PL": "Przewodnik lokalny",
    "pt_PT": "Guia local",
}
# After the zone dropdown (40) and clear of the portal's Ferias entry (50).
LOCAL_GUIDE_MENU_SEQUENCE = 55
LOCAL_GUIDE_CHILDREN = (
    ("Memoria Viva", "/explora/memoria-viva", 10),
    ("Lugares de Interés", "/explora/lugares-de-interes", 20),
    ("Reseñas", "https://canariasconectada.es/resenas", 30),
)
LOCAL_GUIDE_PROBE_URL = LOCAL_GUIDE_CHILDREN[1][1]

# Stock menu entries that core copy_menu_hierarchy copies from the template
# menus onto every new website. Production does not give them to merchant
# microsites (see the one-off fix f20_menu_parity), so they are pruned from
# a FRESHLY created website only. Only the stock labels are ever removed:
# a renamed entry is somebody's decision.
STOCK_MENUS_TO_PRUNE = (
    ("/event", ("Eventos", "Events")),
    ("/slides", ("Cursos", "Courses")),
    # Measured on the 206 live merchant microsites: not one links /contactus.
    # The microsite answers contact on its own homepage (the message form and
    # the reachable data of the contact block), so the stock entry core copies
    # over is a second, poorer door to the same thing.
    ("/contactus", ("Contacta con nosotros", "Contact us", "Contáctenos")),
)

# Structural / umbrella company names that must not receive a microsite.
PROTECTED_NAME_PATTERNS = (
    "zona comercial",
    "canarias conectada",
    "my company",
)

# Opening copy seeded into a brand-new microsite. The corporate homepage
# template gates every section on the field that feeds it (``t-if``), so a
# company born with all of them empty publishes a page holding nothing but
# the hero and the contact block -- the merchant sees an empty shell and has
# no clue which fields bring the rest back. These are the defaults the origin
# platform wrote on company creation, mapped to the reformed field names:
# real copy, never Lorem Ipsum, and only ever written into a field that is
# still empty (see _seed_microsite_content_defaults).
MICROSITE_CONTENT_DEFAULTS = {
    "microsite_button_text": "Tienda",
    # Compact notation validated by _check_microsite_opening_hours.
    "microsite_opening_hours": "L-V 09:00-17:00 / S 10:00-12:00",
    "microsite_delivery_info": "Entrega disponible",
    "microsite_parking_info": "Parking cercano",
    # The intro banner is the first of the two full-width strips, and the
    # template hides a strip that has neither title nor image. Website 221
    # published with only the closing one, which reads as a broken page
    # rather than as an empty field. A default title brings the strip back;
    # the merchant replaces it with what they actually sell.
    "microsite_intro_title": "Descubre lo que tenemos para ti",
    "microsite_about_title": "Sobre nosotros",
    "microsite_about_text": (
        "En nuestro espacio encontrarás productos y servicios seleccionados "
        "con dedicación. Visítanos y forma parte de la experiencia Canarias "
        "Conectada."
    ),
    "microsite_services_title": "Nuestros servicios",
    # Deliberately NOT the same copy as the About block: the two sit side by
    # side on the homepage, and repeating one paragraph twice reads as a bug.
    "microsite_services_text": (
        "Atención cercana y asesoramiento honesto sobre lo que ofrecemos. "
        "Cuéntanos qué necesitas y te ayudamos a encontrarlo."
    ),
    "microsite_banner_title": "Consume Productos Canarios",
}


def _normalize_subdomain(name):
    """Return a DNS-safe subdomain built from a company name.

    Accented characters are transliterated to their closest ASCII form
    (e.g. "Panadería Ñandú" -> "panaderianandu") so real business names keep a
    meaningful subdomain instead of having their accented letters dropped.
    """
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    subdomain = re.sub(r"[^a-z0-9\s]", "", ascii_name.lower())
    subdomain = re.sub(r"\s+", "", subdomain)[:30]
    return subdomain or "empresa"


class ResCompany(models.Model):
    _inherit = "res.company"

    microsite_subdomain = fields.Char(
        string="Microsite Subdomain",
        copy=False,
        index=True,
        help=(
            "The DNS label the microsite is published under, without the "
            "domain: type 'neveri' and the site answers at "
            "https://neveri.canariasconectada.es. Set it before the microsite "
            "is created so the DNS record can be prepared first."
        ),
    )
    microsite_address = fields.Char(
        string="Microsite Address",
        compute="_compute_microsite_address",
        help="Full address the microsite answers at, built from the subdomain.",
    )

    @api.depends("microsite_subdomain")
    def _compute_microsite_address(self):
        suffix = self._microsite_domain_suffix()
        for company in self:
            subdomain = company.microsite_subdomain
            company.microsite_address = (
                f"https://{subdomain}{suffix}" if subdomain and suffix else ""
            )

    @api.constrains("microsite_subdomain")
    def _check_microsite_subdomain(self):
        """Reject anything that is not a usable DNS label, and duplicates.

        Validated on the model rather than only in the wizard because the
        field is editable on the company form and reachable from a shell: a
        subdomain that DNS cannot express is a website nobody can visit, and
        two companies sharing one is a website serving the wrong shop.
        """
        for company in self:
            subdomain = company.microsite_subdomain
            if not subdomain:
                continue
            if not SUBDOMAIN_RE.match(subdomain):
                raise ValidationError(
                    _(
                        "'%(subdomain)s' is not a valid subdomain. Use lowercase "
                        "letters, digits and hyphens only (no dots, no spaces, "
                        "no accents), starting and ending with a letter or a "
                        "digit — for example 'neveri' or 'panaderia-luz'.",
                        subdomain=subdomain,
                    )
                )
            clash = self.search(
                [
                    ("microsite_subdomain", "=", subdomain),
                    ("id", "!=", company.id),
                ],
                limit=1,
            )
            if clash:
                raise ValidationError(
                    _(
                        "The subdomain '%(subdomain)s' is already used by "
                        "%(company)s. Two microsites cannot answer at the same "
                        "address.",
                        subdomain=subdomain,
                        company=clash.display_name,
                    )
                )

    # ------------------------------------------------------------------
    # Company creation hook
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        if not self._auto_microsite_is_enabled():
            return companies
        # In "ask" mode a company whose subdomain nobody named is created
        # WITHOUT a website: the operator names it from the company form,
        # after the DNS record exists. Decided per record, not per batch, so a
        # mixed import still works -- rows carrying a subdomain are
        # provisioned, the rest wait. ``companies`` itself is never narrowed:
        # every company created must come back to the caller.
        to_build = companies
        if self._microsite_subdomain_mode() == SUBDOMAIN_MODE_ASK:
            to_build = companies.filtered("microsite_subdomain")
            for company in companies - to_build:
                _logger.info(
                    "No subdomain for %s: the microsite waits until one is "
                    "named on the company form (subdomain_mode=ask).",
                    company.display_name,
                )
        if not to_build:
            return companies
        # Record rules would hide the brand-new companies (they are not in
        # allowed_company_ids yet) while we build their websites, so widen the
        # context for the generation pass only.
        allowed = list(
            self.env.context.get("allowed_company_ids") or self.env.companies.ids
        )
        new_ids = [company.id for company in to_build if company.id not in allowed]
        generation = to_build
        if new_ids:
            generation = to_build.with_context(allowed_company_ids=allowed + new_ids)
        for company in generation:
            # A microsite failure must NEVER abort the company creation. Each
            # generation runs in its own savepoint so a partial write is rolled
            # back cleanly -- otherwise the aborted DB state would also doom the
            # outer create at flush time -- while the company itself survives.
            try:
                with self.env.cr.savepoint():
                    company._auto_generate_microsite()
            except Exception:  # noqa: BLE001 - defensive: log and keep going
                _logger.exception("auto-microsite failed for %s", company.display_name)
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
        # A falsy website_id here means the website is about to be created:
        # the prune pass below only ever runs on that freshly created site.
        fresh = not self.website_id
        website = self._get_or_create_microsite_website()
        if not website:
            return
        migrated = self._microsite_has_migrated_content(website)
        self._seed_microsite_content_defaults()
        self._ensure_microsite_cookie_consent()
        self._ensure_microsite_menu(website, skip=migrated, prune_defaults=fresh)
        self._ensure_microsite_homepage(website)
        self._ensure_microsite_rich_homepage(website)

    # ------------------------------------------------------------------
    # Content defaults
    # ------------------------------------------------------------------
    def _seed_microsite_content_defaults(self):
        """Fill the still-empty microsite content fields with the opening copy.

        Non-destructive by construction: a field the merchant already filled
        is never touched, which also makes a re-run a no-op. The fields belong
        to ``partner_microsite_manager``, so each one is probed against
        ``_fields`` -- this module only depends on ``website`` and must stay
        usable when the corporate homepage is not installed at all.

        Migrated microsites are seeded too: their homepage is the static HTML
        the migration brought, which reads none of these fields, so the write
        cannot alter what they render. It only means that publishing the
        corporate homepage on them later starts from real copy.
        """
        self.ensure_one()
        vals = {
            field: value
            for field, value in MICROSITE_CONTENT_DEFAULTS.items()
            if field in self._fields and not self[field]
        }
        if vals:
            self.write(vals)

    def _ensure_microsite_cookie_consent(self):
        """Give the new microsite the same cookie consent as every other one.

        The platform sets first-party campaign attribution cookies, which
        Odoo only withholds until consent WHEN the cookies bar is enabled;
        with the bar off they are set without asking. The migration turned
        the bar on across the estate, but a microsite created afterwards was
        born without it -- website 221 was, and that is a consent gap, not a
        cosmetic one.

        Delegates to ``partner_microsite_manager``, which owns the whole
        story (it also deletes the stock /cookie-policy page core creates
        alongside the bar and redirects the URL to the real policy). Probed
        with ``hasattr`` so this module keeps depending only on ``website``,
        and cheap on every later run: the sweep searches for websites whose
        bar is still off, which is normally none.
        """
        self.ensure_one()
        Page = self.env["website.page"].sudo()
        if not hasattr(Page, "_pmm_enforce_cookie_consent"):
            return
        try:
            with self.env.cr.savepoint():
                Page._pmm_enforce_cookie_consent()
        except Exception:  # noqa: BLE001 - defensive: log and keep going
            _logger.exception(
                "Cookie consent setup failed for %s; the microsite stays.",
                self.display_name,
            )

    # ------------------------------------------------------------------
    # Guards
    # ------------------------------------------------------------------
    def _auto_microsite_is_enabled(self):
        """False when disabled by context flag or system parameter."""
        if self.env.context.get("no_microsite_auto"):
            return False
        value = self.env["ir.config_parameter"].sudo().get_param(ENABLE_PARAM, "True")
        return str(value).strip().lower() not in ("false", "0", "")

    @api.model
    def _microsite_subdomain_mode(self):
        """``ask`` (default) or ``auto`` -- see :data:`SUBDOMAIN_MODE_PARAM`.

        Anything the parameter holds other than ``auto`` reads as ``ask``:
        the failure mode of a typo should be "you were asked", never "a
        website appeared on a hostname nobody registered".
        """
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(SUBDOMAIN_MODE_PARAM, SUBDOMAIN_MODE_ASK)
        )
        value = str(value).strip().lower()
        return (
            SUBDOMAIN_MODE_AUTO
            if value == SUBDOMAIN_MODE_AUTO
            else (SUBDOMAIN_MODE_ASK)
        )

    @api.model
    def _microsite_domain_suffix(self):
        return self.env["ir.config_parameter"].sudo().get_param(DOMAIN_SUFFIX_PARAM, "")

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
        # Born with the corporate microsite look when partner_microsite_manager
        # is installed. Probed on the field registry so this module keeps
        # depending only on ``website``.
        if "is_microsite_themed" in self.env["website"]._fields:
            values["is_microsite_themed"] = True
        domain = self._microsite_default_domain()
        if domain:
            values["domain"] = domain
        website = self.env["website"].sudo().create(values)
        # res.company.website_id is a stored compute WITHOUT @api.depends, so a
        # bare cache invalidation would clear the value but never reschedule the
        # recompute, leaving website_id stale (False) forever. Flag the field for
        # recomputation instead: the next read runs _compute_website_id and
        # resolves the freshly created website.
        self.env.add_to_compute(self._fields["website_id"], self)
        return website

    def _microsite_default_domain(self):
        """The address the new website is born on.

        The subdomain comes from the field when it is set -- somebody named
        it, and that name is what DNS was pointed at. Only in ``auto`` mode is
        one derived from the company name, and it is written back to the field
        straight away: from then on the record itself tells the truth about
        where the site answers, instead of that truth living only inside a
        regular expression.
        """
        self.ensure_one()
        suffix = self._microsite_domain_suffix()
        if not suffix:
            _logger.warning(
                "Config parameter %s is empty: the website of %s is created "
                "without a domain and is unroutable until the parameter is "
                "set (production convention: '.canariasconectada.es').",
                DOMAIN_SUFFIX_PARAM,
                self.display_name,
            )
            return ""
        subdomain = self.microsite_subdomain
        if not subdomain:
            subdomain = self._microsite_free_subdomain(_normalize_subdomain(self.name))
            self.microsite_subdomain = subdomain
        return f"https://{subdomain}{suffix}"

    def _microsite_free_subdomain(self, base):
        """``base``, or ``base-2``, ``base-3``... until no company holds it.

        Only ever reached in ``auto`` mode. Two merchants whose names
        normalise to the same label is not exotic -- there are several
        "Panaderia" in the estate -- and letting the uniqueness constraint
        fire there would leave the second one with no site at all. In ``ask``
        mode the operator gets a plain error instead, because a silently
        renamed hostname is not something to discover from DNS.
        """
        self.ensure_one()
        candidate, suffix_number = base, 1
        while self.search_count(
            [("microsite_subdomain", "=", candidate), ("id", "!=", self.id)]
        ):
            suffix_number += 1
            candidate = f"{base[:58]}-{suffix_number}"
        return candidate

    # ------------------------------------------------------------------
    # Menu (create-only, never destructive)
    # ------------------------------------------------------------------
    def _ensure_microsite_menu(self, website, skip=False, prune_defaults=False):
        """Ensure the standard top-menu entries exist on ``website``.

        Create-only by design: existing menus are never renamed or removed,
        so migrated navigation and manual edits survive. When the website
        already carries migrated menus the whole step is skipped.

        ``prune_defaults`` is the single exception to create-only, and the
        caller sets it ONLY for a freshly created website: the stock
        Events/Courses entries that core ``copy_menu_hierarchy`` just copied
        onto it are removed (see :data:`STOCK_MENUS_TO_PRUNE`). It is never
        set on an existing website, so navigation someone curated survives.
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
                menu = Menu.create(
                    {
                        "name": label,
                        "url": url,
                        "parent_id": root.id,
                        "website_id": website.id,
                        "sequence": sequence,
                    }
                )
                self._seed_menu_translations(menu, url)
        self._ensure_zone_menu_dropdown(Menu, website, root)
        self._ensure_local_guide_dropdown(Menu, website, root)
        if prune_defaults:
            self._prune_stock_menus(Menu, website)

    def _seed_menu_translations(self, menu, url):
        """Write the estate wording of ``menu`` in every installed language.

        Machine translation has no way to know that "Comercio" is the name of
        the directory and not the noun: it returns Trade, Handel, Commerce,
        and website 221 went live saying exactly that. The wording of these
        three entries is settled across 206 live microsites, so it is written
        here rather than guessed there.

        Only languages actually installed are written -- writing a language
        Odoo does not know raises -- and the base language is left to the
        ``name`` the menu was created with, which core already resolved
        through the module translations.
        """
        self.ensure_one()
        labels = MENU_LABELS.get(url)
        if not labels:
            return
        installed = {lang[0] for lang in self.env["res.lang"].get_installed()}
        for lang, label in labels.items():
            if lang in installed:
                menu.with_context(lang=lang).name = label

    def _ensure_zone_menu_dropdown(self, Menu, website, root):
        """Create the "Zonas Comerciales" dropdown when it is missing.

        Create-only, like the rest of the menu step: presence is probed on
        one of the child URLs (not on the parent label) so a renamed
        dropdown is recognised and left alone.
        """
        self.ensure_one()
        if Menu.search_count(
            [("website_id", "=", website.id), ("url", "=", ZONE_MENU_PROBE_URL)]
        ):
            return
        parent = Menu.create(
            {
                "name": ZONE_MENU_NAME,
                "url": "#",
                "parent_id": root.id,
                "sequence": ZONE_MENU_SEQUENCE,
                "website_id": website.id,
            }
        )
        Menu.create(
            [
                {
                    "name": name,
                    "url": url,
                    "parent_id": parent.id,
                    "sequence": sequence,
                    "website_id": website.id,
                }
                for name, url, sequence in ZONE_MENU_CHILDREN
            ]
        )

    def _ensure_local_guide_dropdown(self, Menu, website, root):
        """Create the "Guía Local" dropdown when it is missing.

        Same contract as the zone dropdown: create-only, presence probed on
        a child URL so a renamed dropdown is recognised and left alone. The
        children get their estate wording in every installed language.
        """
        self.ensure_one()
        if Menu.search_count(
            [("website_id", "=", website.id), ("url", "=", LOCAL_GUIDE_PROBE_URL)]
        ):
            return
        parent = Menu.create(
            {
                "name": LOCAL_GUIDE_MENU_NAME,
                "url": "#",
                "parent_id": root.id,
                "sequence": LOCAL_GUIDE_MENU_SEQUENCE,
                "website_id": website.id,
            }
        )
        installed = {lang[0] for lang in self.env["res.lang"].get_installed()}
        for lang, label in LOCAL_GUIDE_MENU_LABELS.items():
            if lang in installed:
                parent.with_context(lang=lang).name = label
        for name, url, sequence in LOCAL_GUIDE_CHILDREN:
            child = Menu.create(
                {
                    "name": name,
                    "url": url,
                    "parent_id": parent.id,
                    "sequence": sequence,
                    "website_id": website.id,
                }
            )
            self._seed_menu_translations(child, url)

    def _prune_stock_menus(self, Menu, website):
        """Remove the stock Events/Courses entries from a NEW website.

        Mirrors the one-off fix f20_menu_parity: production does not link
        ``/event`` (nor ``/slides``) from merchant microsites, but core
        ``copy_menu_hierarchy`` copies both onto every new website. Guarded
        twice, like f20: entries not carrying the stock label are kept (a
        renamed menu is somebody's decision) and entries with children are
        kept. Only ever called for the website this very generation pass
        just created, so no curated navigation can be lost.
        """
        self.ensure_one()
        for url, stock_labels in STOCK_MENUS_TO_PRUNE:
            for menu in Menu.search(
                [("website_id", "=", website.id), ("url", "=", url)]
            ):
                if menu.name not in stock_labels or menu.child_id:
                    continue
                menu.unlink()

    # ------------------------------------------------------------------
    # Homepage
    # ------------------------------------------------------------------
    def _get_generic_microsite_homepage_arch(self):
        """Thin homepage wrapper calling the shared microsite content template.

        Returned as canonical XML (no trailing newline): ir.ui.view re-serializes
        arch_db on write, so keeping this a fixed point of that serialization is
        what makes :meth:`_ensure_microsite_homepage` a true idempotent no-op.

        Named "generic" on purpose: ``partner_microsite_manager`` defines its
        own ``_get_microsite_homepage_arch`` on this very model, and with both
        modules installed a shared name would be resolved by module load
        order -- whichever loads last would silently shadow the other.
        """
        self.ensure_one()
        return (
            f'<t name="Homepage" t-name="auto_microsite_generator.homepage_{self.id}">\n'
            '    <t t-call="website.layout">\n'
            '        <div id="wrap" class="oe_structure">\n'
            "            <t t-call="
            '"auto_microsite_generator.default_homepage_content"/>\n'
            "        </div>\n"
            "    </t>\n"
            "</t>"
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
        if page and page.view_id.key == self._microsite_rich_homepage_key():
            # The rich corporate homepage (partner_microsite_manager) already
            # supersedes the generic one: rewriting it back would undo
            # _ensure_microsite_rich_homepage and churn the view on re-runs.
            if not page.is_published:
                page.is_published = True
            return page
        arch = self._get_generic_microsite_homepage_arch()
        view_key = f"auto_microsite_generator.homepage_{self.id}"
        if page:
            # Idempotent refresh: only write what actually changed so re-runs do
            # not churn the view (needless write_date bumps, COW copies, ...).
            # ``arch`` is canonical XML, so it round-trips equal to the stored
            # arch_db and this comparison stays a reliable no-op.
            vals = {}
            if page.view_id.arch_db != arch:
                vals["arch_db"] = arch
            if page.view_id.key != view_key:
                vals["key"] = view_key
            if vals:
                page.view_id.write(vals)
            if not page.is_published:
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

    def _microsite_rich_homepage_key(self):
        """View key ``partner_microsite_manager`` gives this company's homepage."""
        self.ensure_one()
        return f"partner_microsite_manager.microsite_homepage_{self.id}"

    def _ensure_microsite_rich_homepage(self, website):
        """Upgrade the generic homepage to the corporate microsite homepage.

        ``partner_microsite_manager`` ships the dynamic corporate homepage
        and its publication machinery. When it is installed, a brand-new
        microsite is born with that rich homepage instead of the generic
        hero; when it is not, the generic homepage from
        :meth:`_ensure_microsite_homepage` stays. Probed with ``hasattr`` so
        this module keeps depending only on ``website``.

        The publication runs in its own nested savepoint: the per-company
        savepoint of :meth:`create` already shields the company creation,
        but a failure here must not take the website and its generic
        homepage down with it either.
        """
        self.ensure_one()
        if not hasattr(self, "_publish_microsite_homepage"):
            return
        page = (
            self.env["website.page"]
            .sudo()
            .search([("website_id", "=", website.id), ("url", "=", "/")], limit=1)
        )
        if page and (
            self._is_migrated_record(page) or self._is_migrated_record(page.view_id)
        ):
            return
        if page and page.view_id.key == self._microsite_rich_homepage_key():
            # Already the corporate homepage: publishing again would only
            # churn the view (write_date bumps, COW copies, ...).
            return
        try:
            with self.env.cr.savepoint():
                self._publish_microsite_homepage(website)
        except Exception:  # noqa: BLE001 - defensive: log and keep going
            _logger.exception(
                "Rich homepage publication failed for %s; the generic "
                "homepage stays.",
                website.name,
            )
