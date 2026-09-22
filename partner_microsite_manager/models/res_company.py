# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
from datetime import datetime
from urllib.parse import urlsplit

import pytz
from lxml import etree

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.translate import LazyTranslate

from ..tools.opening_hours import (
    MAX_RANGES_PER_DAY,
    format_opening_hours,
    parse_opening_hours,
    slots_from_parsed,
)

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)

# The static hours card the 2026 legacy importer baked into every migrated
# homepage (``build_horario_accordion`` in ``rebuild_microsites_v2026``):
# an accordion with the week's hours as literal HTML plus an inline script.
# It never read the company, which is why editing the hours in the backend
# changed nothing on the site. ``_relink_legacy_opening_hours_card`` swaps
# that element -- and only that element -- for the dynamic card template.
LEGACY_HOURS_CARD_CLASS = "horario-card-accordion"
OPENING_HOURS_CARD_TEMPLATE = "partner_microsite_manager.microsite_opening_hours_card"

# Only https map URLs are embeddable in the microsite contact iframe. A
# 'javascript:' or 'data:' src would run in the visitor's page context
# (stored XSS), so any explicit non-https scheme is refused at write time.
_ALLOWED_MAP_URL_SCHEMES = ("https",)

# Timezone the "open now" badge is judged against. NOT partner_id.tz: that
# field holds whatever timezone the user who created the company happened to
# have (the whole cutover batch carries America/Caracas), and a contact's
# personal timezone is nobody's opening hours. Every merchant of the platform
# trades in the Canary Islands; the parameter exists for the day that stops
# being true.
MICROSITE_TIMEZONE_PARAM = "partner_microsite_manager.microsite_timezone"
_DEFAULT_MICROSITE_TIMEZONE = "Atlantic/Canary"

# Badge labels. Bound to this module with _lt like WEEKDAY_LABELS above: the
# bare _() has to infer the module from the call stack and came back with the
# English source at render time, so the badge said "Open now" on a Spanish
# page while the weekday beside it read "Jueves".
_OPEN_NOW_LABEL = _lt("Open now")
_CLOSED_LABEL = _lt("Closed")

# Weekday names shown on the public microsite, indexed like date.weekday().
# Wrapped in _lt (lazy translation): these are module-level constants
# evaluated at import time, so a plain _() would freeze the English source;
# _lt defers the lookup to render time, when the visitor's es_ES is active.
WEEKDAY_LABELS = (
    _lt("Monday"),
    _lt("Tuesday"),
    _lt("Wednesday"),
    _lt("Thursday"),
    _lt("Friday"),
    _lt("Saturday"),
    _lt("Sunday"),
)


class ResCompany(models.Model):
    _inherit = "res.company"

    # ------------------------------------------------------------------
    # Microsite content, edited on the company form ("Microsite" tab).
    # The public homepage template reads these fields at render time, so
    # saving the form is enough to update the live microsite.
    # ------------------------------------------------------------------
    has_microsite = fields.Boolean(
        compute="_compute_has_microsite",
        help="True when the company has its own website, i.e. a microsite.",
    )
    # Not the company's trade name: that one is `comercial`, on the company
    # itself (`res_company_zone`), and two fields labelled "Trade name" on
    # one form is a question, not a form. This is the heading the microsite
    # prints, which a merchant may well want to word differently.
    microsite_name = fields.Char(
        string="Microsite Heading",
        help="Heading printed on the microsite homepage. Falls back to the "
        "company name. The shop's trade name lives on the company itself.",
    )
    microsite_button_text = fields.Char(
        string="Hero Button Label",
        help="Label of the call-to-action button of the hero section. "
        "Falls back to 'Shop'.",
    )
    microsite_hero_image = fields.Image(string="Hero Image")
    microsite_intro_title = fields.Char(string="Intro Banner Title")
    microsite_intro_image = fields.Image(string="Intro Banner Image")
    microsite_banner_title = fields.Char(string="Closing Banner Title")
    microsite_banner_image = fields.Image(string="Closing Banner Image")
    # The schedule as rows, which is how a merchant edits it since
    # 19.0.2.8.0 ("El campo horario no lo entiendo", 2026-09-15). The text
    # below is generated from them; the public templates keep reading the
    # text, so nothing downstream had to change.
    microsite_opening_slot_ids = fields.One2many(
        comodel_name="microsite.opening.slot",
        inverse_name="company_id",
        string="Opening Periods",
        copy=False,
    )
    # Computed but writable: a company WITH slots always carries the text
    # generated from them; a company WITHOUT slots keeps whatever text it
    # has (the legacy free notation, still validated by the constraint
    # below), so nothing is lost for the shops the migration could not
    # convert.
    microsite_opening_hours = fields.Char(
        string="Opening Hours",
        compute="_compute_microsite_opening_hours",
        store=True,
        readonly=False,
        help="Compact notation, e.g. "
        "L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00 "
        "(L M X J V S D = Monday..Sunday). Generated from the opening "
        "periods when the company has any.",
    )
    microsite_delivery_info = fields.Char(string="Delivery / Shipping")
    microsite_parking_info = fields.Char(string="Parking / Directions")
    microsite_about_title = fields.Char(string="About Title")
    microsite_about_text = fields.Text(string="About Text")
    microsite_services_title = fields.Char(string="Services Title")
    microsite_services_text = fields.Text(string="Services Text")
    microsite_map_url = fields.Char(
        string="Custom Map URL",
        help="Embeddable map URL. When empty, a Google Maps embed is built "
        "from the company address.",
    )
    # Public contact numbers, separate from the partner's own ``phone``.
    # A shop often publishes a counter number while the partner record keeps
    # the number used for orders and paperwork; the origin platform modelled
    # exactly that with two dedicated microsite fields, and the microsite
    # showed ``microsite_phone or partner.phone`` plus an optional second
    # line. Both are kept here so publishing a homepage never has to choose
    # between the public number and the administrative one.
    microsite_phone = fields.Char(
        string="Public Phone",
        help="Phone shown on the microsite. Falls back to the company "
        "contact's phone when empty.",
    )
    microsite_phone2 = fields.Char(
        string="Public Phone 2",
        help="Second phone shown on the microsite, below the first one.",
    )
    # What the footer prints for each network: the website's link first,
    # the company's as the fallback (``microsite_corporate_footer``). The
    # company form shows these rather than the bare ``social_*`` fields, which
    # a website value would silently override; saving writes both sides,
    # exactly as the merchant's content editor does.
    microsite_social_facebook = fields.Char(
        string="Microsite Facebook",
        compute="_compute_microsite_social",
        inverse="_inverse_microsite_social",
    )
    microsite_social_instagram = fields.Char(
        string="Microsite Instagram",
        compute="_compute_microsite_social",
        inverse="_inverse_microsite_social",
    )
    microsite_social_twitter = fields.Char(
        string="Microsite X/Twitter",
        compute="_compute_microsite_social",
        inverse="_inverse_microsite_social",
    )
    microsite_social_youtube = fields.Char(
        string="Microsite YouTube",
        compute="_compute_microsite_social",
        inverse="_inverse_microsite_social",
    )
    microsite_social_linkedin = fields.Char(
        string="Microsite LinkedIn",
        compute="_compute_microsite_social",
        inverse="_inverse_microsite_social",
    )
    microsite_homepage_page_id = fields.Many2one(
        "website.page",
        string="Microsite Homepage",
        readonly=True,
        copy=False,
        help="Homepage published by the 'Publish Homepage' action.",
    )

    _MICROSITE_SOCIAL_FIELDS = (
        "social_facebook",
        "social_instagram",
        "social_twitter",
        "social_youtube",
        "social_linkedin",
    )

    @api.depends(
        *_MICROSITE_SOCIAL_FIELDS,
        *(f"website_id.{name}" for name in _MICROSITE_SOCIAL_FIELDS),
    )
    def _compute_microsite_social(self):
        for company in self:
            website = company.website_id
            for name in self._MICROSITE_SOCIAL_FIELDS:
                company[f"microsite_{name}"] = (
                    (website and website[name]) or company[name] or False
                )

    def _inverse_microsite_social(self):
        for company in self:
            values = {
                name: company[f"microsite_{name}"] or False
                for name in self._MICROSITE_SOCIAL_FIELDS
            }
            company.write(values)
            # The website side wins in the footer, so an emptied value has
            # to reach it too, or the old link keeps rendering.
            if company.website_id:
                company.website_id.write(values)

    @api.depends("website_id")
    def _compute_has_microsite(self):
        for company in self:
            company.has_microsite = bool(company.website_id)

    @api.depends(
        "microsite_opening_slot_ids.weekday",
        "microsite_opening_slot_ids.open_time",
        "microsite_opening_slot_ids.close_time",
    )
    def _compute_microsite_opening_hours(self):
        for company in self:
            slots = company.microsite_opening_slot_ids
            if slots:
                company.microsite_opening_hours = format_opening_hours(
                    (slot.weekday, slot.open_time, slot.close_time) for slot in slots
                )
            else:
                # No rows: keep the stored text as it is (the legacy free
                # notation of a shop the migration could not convert).
                # Deleting the last row is handled by
                # ``microsite.opening.slot.unlink``, which clears the text.
                # Reading the field inside its own compute is safe here --
                # the record is protected, so the ORM serves the stored value.
                company.microsite_opening_hours = company.microsite_opening_hours

    @api.constrains("microsite_opening_hours")
    def _check_microsite_opening_hours(self):
        for company in self:
            value = company.microsite_opening_hours
            if not value:
                continue
            parsed = parse_opening_hours(value)
            if parsed is None:
                raise ValidationError(
                    _(
                        "Invalid opening hours format. Expected e.g. "
                        "'L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00'."
                    )
                )
            if company.microsite_opening_slot_ids:
                # Generated from rows the slot model already validated
                # (ordered, non-overlapping). The per-day cap below is a
                # guard for free text, and "as many periods as the shop
                # needs" is the whole point of the rows.
                continue
            for day, ranges in parsed.items():
                if len(ranges) > MAX_RANGES_PER_DAY:
                    raise ValidationError(
                        _(
                            "Too many time ranges for %(day)s: at most "
                            "%(limit)s per day (morning and afternoon).",
                            day=WEEKDAY_LABELS[day],
                            limit=MAX_RANGES_PER_DAY,
                        )
                    )

    @api.constrains("microsite_map_url")
    def _check_microsite_map_url(self):
        for company in self:
            url = company.microsite_map_url
            if not url:
                continue
            # urlsplit strips tab/newline characters first, so obfuscated
            # 'java\tscript:' payloads are normalised before the check.
            scheme = urlsplit(url.strip()).scheme.lower()
            # An empty scheme is a relative URL that _get_microsite_map_url()
            # upgrades to https at render time, so it is allowed here.
            if scheme and scheme not in _ALLOWED_MAP_URL_SCHEMES:
                raise ValidationError(
                    _(
                        "The map URL must be an https:// address; "
                        "'%(scheme)s:' links are not allowed.",
                        scheme=scheme,
                    )
                )

    # ------------------------------------------------------------------
    # Template helpers (called from QWeb at render time)
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_map_url(url):
        """Return ``url`` with a default https scheme when it has none.

        The ``_check_microsite_map_url`` constraint guarantees the stored
        value is either scheme-less or already https, so this only ever
        prepends a scheme; it never turns a rejected link into a valid one.
        """
        url = (url or "").strip()
        if not url:
            return ""
        if url.startswith("//"):
            return "https:" + url
        if not urlsplit(url).scheme:
            return "https://" + url
        return url

    def _get_microsite_opening_hours_rows(self):
        """Weekly schedule as ``[(day_index, day_label, 'HH:MM - HH:MM'), ...]``.

        Only the days with opening hours are returned, in week order. The
        index is ``date.weekday()`` (Monday = 0) and is what lets the pill
        highlight today's row from the browser.
        """
        self.ensure_one()
        parsed = parse_opening_hours(self.microsite_opening_hours)
        if not parsed:
            return []
        return [
            (
                day,
                WEEKDAY_LABELS[day],
                " / ".join(f"{start} - {end}" for start, end in parsed[day]),
            )
            for day in sorted(parsed)
        ]

    def _get_microsite_opening_hours_lines(self):
        """Weekly schedule as ``[(day_label, 'HH:MM - HH:MM / ...'), ...]``.

        Kept as the label/hours pair the rest of the codebase already
        consumes; :meth:`_get_microsite_opening_hours_rows` is the same data
        with the weekday index in front.
        """
        self.ensure_one()
        return [
            (label, hours)
            for _index, label, hours in self._get_microsite_opening_hours_rows()
        ]

    def _get_microsite_opening_hours_pill(self):
        """Everything the opening-hours pill needs, or ``{}`` when there is
        nothing to show.

        ``today_label`` / ``today_text`` are rendered server-side so the pill
        is never blank for a visitor with JavaScript off. ``payload`` carries
        the whole week to the browser, which re-decides "today" and the
        open/closed badge from the visitor's clock: the homepage can sit in a
        worker cache for a long while, and a shop still claiming "open now"
        at midnight is worse than a pill that says nothing.

        ``days`` inside the payload is indexed like ``date.weekday()``
        (Monday = 0); a day the merchant left out keeps an empty ``ranges``
        so the browser renders it as closed.
        """
        self.ensure_one()
        parsed = parse_opening_hours(self.microsite_opening_hours)
        if not parsed:
            return {}
        timezone = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(MICROSITE_TIMEZONE_PARAM, _DEFAULT_MICROSITE_TIMEZONE)
        )
        try:
            today = datetime.now(pytz.timezone(timezone)).weekday()
        except pytz.UnknownTimeZoneError:
            # A typo in the parameter must not take the pill down.
            timezone = _DEFAULT_MICROSITE_TIMEZONE
            today = datetime.now(pytz.timezone(timezone)).weekday()
        closed = str(_CLOSED_LABEL)
        as_text = lambda ranges: " / ".join(  # noqa: E731
            f"{start} - {end}" for start, end in ranges
        )
        return {
            "rows": self._get_microsite_opening_hours_rows(),
            "today_label": str(WEEKDAY_LABELS[today]),
            "today_text": as_text(parsed[today]) if parsed.get(today) else closed,
            "payload": json.dumps(
                {
                    "timezone": timezone,
                    "openLabel": str(_OPEN_NOW_LABEL),
                    "closedLabel": closed,
                    "days": [
                        {
                            # str() resolves the lazy translation in the
                            # language of the request being rendered.
                            "label": str(WEEKDAY_LABELS[day]),
                            "ranges": [list(hours) for hours in parsed.get(day, [])],
                        }
                        for day in range(7)
                    ],
                }
            ),
        }

    # ------------------------------------------------------------------
    # Opening hours: text -> rows, and the legacy homepage card
    # ------------------------------------------------------------------
    def _sync_slots_from_text(self):
        """Create the opening rows of every company that only has the text.

        Idempotent: a company that already has rows is left alone, and so
        is one with no text. A text the parser refuses -- or one that parses
        into overlapping periods -- keeps its text untouched and is reported
        back, so the merchant can redo it in the new editor.

        Returns ``(synced, unparsed)`` recordsets. Used by the 19.0.2.8.0
        post-migration and by the editor when it opens a shop the migration
        has not seen.
        """
        Slot = self.env["microsite.opening.slot"].sudo()
        synced_ids, unparsed_ids = [], []
        for company in self.sudo():
            text = company.microsite_opening_hours
            if not text or company.microsite_opening_slot_ids:
                continue
            parsed = parse_opening_hours(text)
            if parsed is None:
                unparsed_ids.append(company.id)
                continue
            try:
                with self.env.cr.savepoint():
                    Slot.create(
                        [
                            {
                                "company_id": company.id,
                                "weekday": str(weekday),
                                "open_time": open_time,
                                "close_time": close_time,
                            }
                            for weekday, open_time, close_time in slots_from_parsed(
                                parsed
                            )
                        ]
                    )
            except ValidationError:
                unparsed_ids.append(company.id)
                continue
            synced_ids.append(company.id)
        return self.browse(synced_ids), self.browse(unparsed_ids)

    def _relink_legacy_opening_hours_card(self):
        """Point the legacy homepage's hours card at the company.

        The 2026 importer wrote every migrated homepage as static HTML, hours
        included (``div.horario-card-accordion`` with the week spelled out
        and an inline script deciding "Abierto ahora"). 210 of the 211 live
        homepages are such pages, so the content editor wrote the company
        and the site never noticed -- the 2026-09-15 complaint.

        This replaces that one element with a ``t-call`` of the dynamic card
        template, on the ``/`` page of each of the company's websites. The
        rest of the page -- the merchant's own edits included -- is not
        touched, and a page without the card is skipped. Idempotent: once
        swapped, the class is gone and the page is skipped next time.

        Returns the companies whose homepage was changed.
        """
        Page = self.env["website.page"].sudo()
        Website = self.env["website"].sudo()
        relinked_ids = []
        for company in self:
            websites = company.website_id | Website.search(
                [("company_id", "=", company.id)]
            )
            # Every page at "/" of the site, not the first one: a website
            # bootstraps a "Home" of its own on creation, and the imported
            # legacy homepage sits next to it as a second record.
            pages = Page.search([("website_id", "in", websites.ids), ("url", "=", "/")])
            # lang=None: the base (en_US) arch is what gets rewritten; the
            # translated copies re-map their unchanged terms.
            for view in pages.view_id.with_context(lang=None):
                arch = view.arch_db or ""
                if LEGACY_HOURS_CARD_CLASS not in arch:
                    continue
                # One page at a time: a homepage the importer left as
                # something lxml refuses, or one the view validation
                # rejects, keeps its card and is logged; it must not take
                # the other 210 sites' upgrade down with it.
                try:
                    with self.env.cr.savepoint():
                        if self._swap_legacy_opening_hours_card(view, arch):
                            if company.id not in relinked_ids:
                                relinked_ids.append(company.id)
                except (etree.XMLSyntaxError, ValueError, ValidationError):
                    _logger.exception(
                        "Opening hours: could not relink the legacy card of "
                        "view %s (company %s); the page keeps its static hours.",
                        view.id,
                        company.id,
                    )
        return self.browse(relinked_ids)

    @api.model
    def _swap_legacy_opening_hours_card(self, view, arch):
        """Replace the legacy card(s) in ``arch`` and write it back to
        ``view``. Returns whether anything was replaced."""
        tree = etree.fromstring(arch.encode("utf-8"))
        cards = tree.xpath(
            "//*[contains(concat(' ', normalize-space(@class), ' '), "
            f"' {LEGACY_HOURS_CARD_CLASS} ')]"
        )
        replaced = False
        for card in cards:
            parent = card.getparent()
            if parent is None:
                # A card nested inside a card already swapped out.
                continue
            call = etree.Element("t")
            call.set("t-call", OPENING_HOURS_CARD_TEMPLATE)
            call.tail = card.tail
            parent.replace(card, call)
            replaced = True
        if replaced:
            view.write({"arch_db": etree.tostring(tree, encoding="unicode")})
        return replaced

    def _get_microsite_website_url(self):
        """The shop's own site as a clickable absolute URL, or ``""``.

        Merchants type ``myshop.com`` as often as they type the full URL,
        and a bare host in an href is read as a relative path -- the link
        would point back into the microsite.
        """
        self.ensure_one()
        url = (self.partner_id.website or "").strip()
        if not url:
            return ""
        if "://" not in url:
            return "https://" + url
        return url

    def _get_microsite_website_host(self):
        """The host of the shop's own site (``www.myshop.com``), or ``""``.

        What the contact block and the footer show as text: the address a
        visitor can read, not the scheme and path they cannot.
        """
        self.ensure_one()
        url = self._get_microsite_website_url()
        return urlsplit(url).netloc if url else ""

    def _get_microsite_map_url(self):
        """Embeddable map URL: the custom one, or one built from the address.

        Returns an empty string when there is nothing to show, so the
        template hides the map block entirely.
        """
        self.ensure_one()
        custom_url = self._normalize_map_url(self.microsite_map_url)
        if custom_url:
            return custom_url
        # Same builder as the event pages (website_map_embed), so both maps
        # stay identical.
        return self.partner_id._canarias_map_embed_url() or ""

    # ------------------------------------------------------------------
    # Homepage publication (explicit action, one-time per website)
    # ------------------------------------------------------------------
    def _get_microsite_homepage_arch(self):
        """Arch of the homepage view: a thin wrapper around the dynamic
        content template. All the actual content is rendered at request
        time from the company fields, so this arch never needs a re-sync.
        """
        self.ensure_one()
        return (
            '<t t-name="partner_microsite_manager.'
            f'microsite_homepage_{self.id}">\n'
            '    <t t-call="website.layout">\n'
            '        <div id="wrap" class="oe_structure">\n'
            '            <t t-call="'
            'partner_microsite_manager.microsite_homepage_content"/>\n'
            "        </div>\n"
            "    </t>\n"
            "</t>\n"
        )

    # ------------------------------------------------------------------
    # Self-service: the merchant's own way in
    # ------------------------------------------------------------------
    @api.model
    def _get_own_microsite_company(self):
        """The one shop the caller may edit the page content of.

        ``res.users.company_id`` and nothing else, mirroring the reasoning in
        ``website_directory._get_own_company_for_directory``: the allowed
        companies list is not a statement of ownership on this platform --
        ``zone_company_ownership`` puts the ZONE company in it, and letting a
        merchant edit their neighbourhood's homepage because it happens to be
        in their list is exactly the leak that module was written to close.

        Returns an empty recordset instead of raising, so the caller can say
        "you have no shop" rather than serve a traceback.
        """
        user = self.env.user
        if not user or user._is_public():
            return self.browse()
        company = user.company_id
        if not company or not company.active or not company.website_id:
            return self.browse()
        # The platform's own company is nobody's shop.
        main = self.env.ref("base.main_company", raise_if_not_found=False)
        if main and company == main:
            return self.browse()
        return company

    @api.model
    def write(self, vals):
        """A shop has one logo, and the microsite header shows it.

        The public header reads ``website.logo``; the company form, the
        directory and the self-service screen write ``res.company.logo``
        (the partner image). Two fields, and until 2026-09-14 nothing kept
        them together: a merchant changed their logo and the header kept the
        old one (or Odoo's grey placeholder, on 97 sites). Mirroring it on
        write is the smallest thing that makes "cambio el logo" true
        everywhere the visitor looks.
        """
        result = super().write(vals)
        if "logo" in vals:
            for company in self:
                websites = company.website_id | self.env["website"].sudo().search(
                    [("company_id", "=", company.id)]
                )
                websites.sudo().write({"logo": vals["logo"]})
        return result

    @api.model
    def _action_open_own_websites(self, companies=None):
        """The caller's shops, as a list they can work from.

        Built from ids rather than from a domain on purpose: `website` has
        no record rule of its own here, and it must not get one -- every
        request reads that model, so narrowing it for merchants would break
        their browsing of any site but their own.
        """
        if companies is None:
            companies = self._get_own_microsite_companies()
        websites = (
            self.env["website"].sudo().search([("company_id", "in", companies.ids)])
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("My shops"),
            "res_model": "website",
            "view_mode": "list",
            "views": [
                (
                    self.env.ref(
                        "partner_microsite_manager.website_view_list_merchant"
                    ).id,
                    "list",
                )
            ],
            "domain": [("id", "in", websites.ids)],
            "target": "current",
            "context": {"create": False, "delete": False},
        }

    def _get_own_microsite_companies(self):
        """Every REAL shop the caller may pick the page content of.

        Unlike :meth:`_get_own_microsite_company` (the caller's SESSION
        company, singular, and unchanged), this is the caller's full set of
        real shops: every company in ``user.company_ids`` that is active, has
        its own website, is not the platform's own company, and is not one of
        the bookkeeping zone companies ``zone_company_ownership`` also puts in
        that list -- the allowed-companies list is not a statement of
        ownership on this platform, exactly as the docstring of
        :meth:`_get_own_microsite_company` already explains.

        ``_zone_companies`` is a soft dependency, reached through
        ``hasattr`` rather than a hard ``depends`` on
        ``zone_company_ownership``, mirroring
        ``website_sale_comparison_canarias`` (``models/website.py``).

        Returns an empty recordset instead of raising: an empty picker set is
        a normal, expected outcome (single-shop or zero-shop accounts), never
        an error condition.
        """
        user = self.env.user
        if not user or user._is_public():
            return self.browse()
        companies = user.company_ids.filtered(lambda c: c.active and c.website_id)
        main = self.env.ref("base.main_company", raise_if_not_found=False)
        if main:
            companies -= main
        if hasattr(self, "_zone_companies"):
            companies -= self.sudo()._zone_companies()
        return companies

    def _get_editable_microsite_companies(self):
        """Every company the caller may write page content to, right now.

        The UNION of the picker set (:meth:`_get_own_microsite_companies`)
        and the legacy singular (:meth:`_get_own_microsite_company`) --
        never a replacement of one by the other. Zone staff whose OWN
        session company IS the zone company keep write access today
        (the singular helper never subtracts zones); subtracting zones from
        THIS authorisation set too would silently revoke that. The picker
        only stops ADVERTISING the zone company as something to pick; it
        must never narrow who may already write.

        This is the single authority
        ``microsite.content.editor._resolve_target_company()`` checks
        membership against.
        """
        return self._get_own_microsite_companies() | self._get_own_microsite_company()

    def action_publish_microsite_homepage(self):
        """Create or replace the homepage of the company website with the
        dynamic microsite template.

        Explicit by design: nothing is ever written to a website unless a
        backoffice user pushes the button, and only the company's own
        website can be touched (``website_id`` is the website whose
        ``company_id`` is this company).

        Publishing overwrites a public website homepage through ``sudo`` in
        ``_publish_microsite_homepage``, so it must be gated: only website
        designers may push content live, and only if they can write the
        company record itself. Without this check any authenticated user
        could replace the homepage.
        """
        if not self.env.user.has_group("website.group_website_designer"):
            raise AccessError(
                _("Only website designers can publish a microsite homepage.")
            )
        self.check_access("write")
        for company in self:
            website = company.website_id
            if not website:
                raise UserError(
                    _(
                        "Company %(name)s has no website yet. Create its "
                        "website first (Settings > Websites).",
                        name=company.display_name,
                    )
                )
            company._publish_microsite_homepage(website)
        return True

    def _publish_microsite_homepage(self, website):
        self.ensure_one()
        # sudo: microsite editors are not necessarily website designers,
        # and the target website is guaranteed to be the company's own.
        view_model = self.env["ir.ui.view"].sudo()
        page_model = self.env["website.page"].sudo()
        arch = self._get_microsite_homepage_arch()
        view_key = f"partner_microsite_manager.microsite_homepage_{self.id}"
        page = page_model.search(
            [("website_id", "=", website.id), ("url", "=", "/")], limit=1
        )
        if page:
            page.view_id.write({"arch_db": arch, "key": view_key})
        else:
            view = view_model.create(
                {
                    "name": f"Microsite Homepage - {self.name}",
                    "type": "qweb",
                    "key": view_key,
                    "arch_db": arch,
                    "website_id": website.id,
                }
            )
            page = page_model.create(
                {
                    "name": f"Microsite Homepage - {self.name}",
                    "url": "/",
                    "view_id": view.id,
                    "website_id": website.id,
                    "is_published": True,
                }
            )
        page.is_published = True
        self.microsite_homepage_page_id = page
