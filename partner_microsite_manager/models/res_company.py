# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging
import re
from datetime import datetime
from urllib.parse import parse_qs, quote_plus, urlsplit

import pytz
from lxml import etree

from odoo import SUPERUSER_ID, _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.sql import column_exists
from odoo.tools.translate import LazyTranslate

from odoo.addons.website_map_embed.models.res_partner import (
    clean_address_part,
    street_without_zip,
)

from ..tools import legacy_homepage
from ..tools import map_url as map_url_tools
from ..tools.opening_hours import (
    MAX_RANGES_PER_DAY,
    format_opening_hours,
    parse_opening_hours,
    slots_from_parsed,
)
from ..tools.safe_url import safe_http_url

_lt = LazyTranslate(__name__)
_logger = logging.getLogger(__name__)

# The static hours card the 2026 legacy importer baked into every migrated
# homepage (``build_horario_accordion`` in ``rebuild_microsites_v2026``):
# an accordion with the week's hours as literal HTML plus an inline script.
# It never read the company, which is why editing the hours in the backend
# changed nothing on the site. ``_relink_legacy_opening_hours_card`` swaps
# that element -- and only that element -- for the dynamic card template.
LEGACY_HOURS_CARD_CLASS = legacy_homepage.LEGACY_HOURS_CARD_CLASS
OPENING_HOURS_CARD_TEMPLATE = legacy_homepage.OPENING_HOURS_CARD_TEMPLATE

# The imported homepages: the views of the "/" pages whose key the importer
# chose. The dynamic homepage (``partner_microsite_manager.microsite_homepage_*``)
# and theme homepages (company 100's ``theme_corporate_multi``) never match.
LEGACY_HOMEPAGE_KEY_LIKE = ("website.homepage\\_%", "website.home-%")
LEGACY_HOMEPAGE_KEY_RE = re.compile(r"^website\.(homepage_|home-)")
# Set by ``_normalize_existing_map_urls``: a link converted by the cron is
# not a person choosing a map, so the page is not relinked.
MAP_NORMALIZE_CONTEXT_KEY = "pmm_map_normalize"
# Attachment the 19.0.2.13.0 migration stores the original arch_db in.
LEGACY_BACKUP_NAME = "legacy-homepage-backup-{view_id}-19.0.2.13.0.json"
# Set while the relinker writes a page, so the builder-save guard on
# ``ir.ui.view.write`` does not run again on its own write.
LIVE_RELINK_CONTEXT_KEY = "pmm_live_relink"
# The company fields the live blocks of a legacy homepage render: writing
# any of them has to drop the one-hour page cache.
LIVE_COMPANY_FIELDS = frozenset(
    {
        "microsite_phone",
        "microsite_phone2",
        "microsite_parking_info",
        "microsite_delivery_info",
        "microsite_map_url",
        "microsite_map_share_url",
        "microsite_opening_hours",
        "microsite_opening_slot_ids",
    }
)

# Only https map URLs are embeddable in the microsite contact iframe. A
# 'javascript:' or 'data:' src would run in the visitor's page context
# (stored XSS), so any explicit non-https scheme is refused at write time.
_ALLOWED_MAP_URL_SCHEMES = ("https",)
# The pasted original only ever feeds an ``href``: http(s), nothing else.
_ALLOWED_MAP_SHARE_URL_SCHEMES = ("http", "https")
# Short links the daily retry resolves per run (each is up to one network
# resolution, see ``tools.map_url.RESOLVE_BUDGET``).
MAP_RETRY_BATCH = 20
# Companies whose non-embeddable map this process already reported: the
# render fallback runs on every page view, the warning only needs to be
# read once.
_MAP_FALLBACK_REPORTED = set()

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


def clear_templates_cache_on_commit(env):
    """Empty the page/template cache once, when the transaction commits.

    The public pages are cached for an hour per page; clearing on every
    write would empty it for the whole platform many times per save, and
    clearing before the commit lets a concurrent request cache the old
    values again. ``retrying`` runs the post-commit hooks before it signals
    the registry changes, so the other workers hear about it. Bounded: only
    writes that really change a rendered value get here, and at most one
    clear happens per committed transaction.
    """
    postcommit = env.cr.postcommit
    if postcommit.data.get(_CLEAR_CACHE_KEY):
        return
    postcommit.data[_CLEAR_CACHE_KEY] = True
    registry = env.registry
    postcommit.add(lambda: registry.clear_cache("templates"))


_CLEAR_CACHE_KEY = "partner_microsite_manager.clear_templates_cache"
# Contexts of bulk operations (module install/upgrade, data import) in which
# a contact change must not rewrite pages.
BULK_CONTEXT_KEYS = ("install_mode", "module", "import_file")


def _live_values_change(records, field_names, vals):
    """Whether writing ``vals`` changes one of ``field_names`` on ``records``.

    Empty values compare equal (``False``, ``""``, ``None``); a relational
    command is always a change.
    """
    for name in field_names.intersection(vals):
        if records._fields[name].type in ("one2many", "many2many"):
            return True
        new = vals[name] or False
        if any((record[name] or False) != new for record in records):
            return True
    return False


class _TranslationMismatch(Exception):
    """A relink would have changed a language copy beyond its values."""


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
        help="Paste any Google Maps link (share or embed); it will be "
        "converted automatically. When empty, the map is built from the "
        "company address.",
    )
    # What the user pasted, when it had to be converted to be framed (a
    # share link, a place page): the "View on Google Maps" link goes there.
    microsite_map_share_url = fields.Char(
        string="Google Maps Link",
        help="The link that was pasted as the map, before it was converted "
        "to an embeddable one.",
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

    @api.constrains("microsite_map_share_url")
    def _check_microsite_map_share_url(self):
        for company in self:
            url = company.microsite_map_share_url
            if not url:
                continue
            scheme = urlsplit(url.strip()).scheme.lower()
            if scheme and scheme not in _ALLOWED_MAP_SHARE_URL_SCHEMES:
                raise ValidationError(
                    _(
                        "The Google Maps link must be an http:// or https:// "
                        "address; '%(scheme)s:' links are not allowed.",
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
        Anything that is not http(s) -- a value stored before the
        constraint existed, or written around it -- gives ``""``, so the
        iframe falls back to the address map (``tools/safe_url``).
        """
        return safe_http_url(url)

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
        tree = etree.fromstring(
            arch.encode("utf-8"), parser=legacy_homepage.safe_parser()
        )
        replaced = legacy_homepage.swap_legacy_hours_cards(tree)
        if replaced:
            # Flagged: on an upgrade from before 19.0.2.8.0 the builder-save
            # guard must not relink the page before 19.0.2.13.0 backed it up.
            view.with_context(**{LIVE_RELINK_CONTEXT_KEY: True}).write(
                {"arch_db": etree.tostring(tree, encoding="unicode")}
            )
        return replaced

    # ------------------------------------------------------------------
    # Legacy homepages: every value read from the company
    # ------------------------------------------------------------------
    @staticmethod
    def _get_microsite_tel_href(number):
        """``tel:`` link for a number as the merchant typed it."""
        digits = re.sub(r"[^\d+]", "", number or "")
        return f"tel:{digits}" if digits else ""

    def _get_microsite_live_address(self):
        """One line: ``street, street2, zip city``.

        The importer left a literal ``&nbsp;`` (and the zip again) in some
        streets -- ``Calle X 23&nbsp;35010`` -- which QWeb would print
        escaped; it is decoded, and a zip the street repeats is dropped.
        """
        self.ensure_one()
        partner = self.partner_id

        def clean(value):
            # Same cleaning as the map query (website_map_embed).
            return clean_address_part(value).strip(" ,")

        zip_code, city = clean(partner.zip), clean(partner.city)
        street = street_without_zip(clean(partner.street), zip_code)
        locality = " ".join(part for part in (zip_code, city) if part)
        return ", ".join(
            part for part in (street, clean(partner.street2), locality) if part
        )

    def _microsite_live_has(self, kind):
        """Whether the shop has the value a live block of ``kind`` shows.

        Called from the ``t-if`` the relinker puts on each line and card of
        a legacy homepage, so an emptied value takes its label with it.
        """
        self.ensure_one()
        partner = self.partner_id
        if kind == "address":
            return bool(self._get_microsite_live_address())
        if kind == "phone":
            return bool(self.microsite_phone or partner.phone)
        if kind == "phone2":
            return bool(self.microsite_phone2)
        if kind == "email":
            return bool(partner.email)
        if kind == "website":
            return bool(self._get_microsite_website_url())
        if kind == "map":
            return bool(self._get_microsite_map_url())
        if kind == "hours":
            return bool(parse_opening_hours(self.microsite_opening_hours))
        if kind in ("parking", "delivery"):
            return bool(self[f"microsite_{kind}_info"])
        if kind == "features":
            return any(
                self._microsite_live_has(name)
                for name in ("hours", "parking", "delivery")
            )
        return False

    def _get_microsite_live_facts(self):
        """``{kind: bool}`` for the relinker (which missing lines to add)."""
        self.ensure_one()
        return {
            kind: self._microsite_live_has(kind)
            for kind in (
                "address",
                "phone",
                "phone2",
                "email",
                "website",
                "map",
                "hours",
            )
        }

    @api.model
    def _get_legacy_homepage_views(self, view_ids=None):
        """The imported homepages to relink, as ``ir.ui.view`` records.

        Resolved in SQL so the migration does not depend on which optional
        modules are loaded: the "/" page of a website, with an importer key,
        whose company is not one of the three zone companies (their homepage
        is a different, hand-built page; ``zone_company_key`` comes from
        ``zone_company_ownership`` and is only looked at when its column
        exists). ``self`` narrows to those companies when not empty;
        ``view_ids`` narrows to those views.
        """
        query = """
            SELECT DISTINCT v.id
              FROM website_page p
              JOIN ir_ui_view v ON v.id = p.view_id
              JOIN website w ON w.id = p.website_id
             WHERE p.url = '/'
               -- Website-specific views only (all 207 on prod are): a
               -- generic view is shared, and the builder's copy-on-write
               -- creates the specific copy it edits rather than writing it.
               AND v.website_id IS NOT NULL
               AND (v.key LIKE %s OR v.key LIKE %s)
        """
        params = list(LEGACY_HOMEPAGE_KEY_LIKE)
        if column_exists(self.env.cr, "res_company", "zone_company_key"):
            query += """
               AND w.company_id NOT IN (
                   SELECT id FROM res_company WHERE zone_company_key IS NOT NULL
               )
            """
        if self:
            query += " AND w.company_id = ANY(%s)"
            params.append(self.ids)
        if view_ids is not None:
            query += " AND v.id = ANY(%s)"
            params.append(list(view_ids))
        self.env.cr.execute(query + " ORDER BY v.id", params)
        return (
            self.env["ir.ui.view"]
            .sudo()
            .browse([row[0] for row in self.env.cr.fetchall()])
        )

    def _get_microsite_live_values(self):
        """What the company says, for the migration's page comparison."""
        self.ensure_one()
        return {
            "email": self.partner_id.email or "",
            "address": self._get_microsite_live_address(),
            "website": self.partner_id.website or "",
            "map": self.microsite_map_url or "",
            "map_explicit": bool(self.microsite_map_url),
        }

    def _relink_legacy_homepage_live_data(self, views=None, mode="migration", kinds=()):
        """Point the values of the legacy homepages at the company.

        The importer typed phone, address, email, map, parking and delivery
        into ~207 homepages, so the content editor saved the company and the
        page never changed (Panambi still offered "Entrega disponible" after
        the merchant emptied it). The design, the long texts and the labels
        stay: only the VALUE nodes become t-calls of the live templates
        (``views/microsite_live_data.xml``), see ``tools/legacy_homepage``.

        "The migration preserves what each page shows; from then on, a human
        edit wins." ``mode``:

        - ``migration`` (19.0.2.13.0): phone, parking, delivery and hours go
          live; email, address, web and map only where the page shows what
          the company says (``report["kept_static"]`` lists the others);
          the hours card is added where the shop has hours and the page
          has none;
        - ``guard`` (a builder save): only what is already live, or was
          flattened by the save, is relinked; nothing is added;
        - ``edit`` (a human changed ``kinds`` on the company or partner):
          those kinds go live on the page whatever it showed.

        ``views`` narrows the run; whatever it holds, only imported
        homepages of non-zone shops are touched (``_get_legacy_homepage_views``).
        One savepoint per page; the base arch is written with ``lang=None``
        so the other languages re-map their unchanged terms, and the write
        is undone when a language copy would lose or gain anything but the
        relinked values (``_check_translation_terms``). Any error is logged
        and the page keeps its arch: a relink never fails the run, the
        builder save or the edit that triggered it. Idempotent.

        Returns one dict per page: ``view_id``, ``company_id``, ``written``,
        ``failed`` and the transformation report (``relinked``,
        ``inserted``, ``dropped``, ``restored``, ``kept_static``, ``notes``,
        ``skipped``).
        """
        assert mode in ("migration", "guard", "edit"), mode
        targets = self._get_legacy_homepage_views(
            view_ids=views.ids if views is not None else None
        )
        stats = []
        for view in targets.with_context(lang=None):
            company = view.website_id.company_id.sudo()
            stat = {
                "view_id": view.id,
                "company_id": company.id,
                "written": False,
                "failed": False,
            }
            report = legacy_homepage.empty_report()
            try:
                with self.env.cr.savepoint():
                    if mode == "migration":
                        new_arch, report = self._relink_from_authoring_copy(
                            view, company
                        )
                    else:
                        new_arch, report = legacy_homepage.relink_live_data(
                            view.arch_db or "",
                            company._get_microsite_live_facts(),
                            force=kinds if mode == "edit" else (),
                        )
                    if new_arch:
                        before = self._get_arch_db_raw(view)
                        view.with_context(
                            lang=None, **{LIVE_RELINK_CONTEXT_KEY: True}
                        ).write({"arch_db": new_arch})
                        problem = self._check_translation_terms(
                            view, before, self._get_arch_db_raw(view)
                        )
                        if problem:
                            raise _TranslationMismatch(problem)
                        stat["written"] = True
            except _TranslationMismatch as mismatch:
                # The savepoint undid the write; the cache still holds it.
                self.env.invalidate_all()
                _logger.warning(
                    "Legacy homepage: view %s (company %s) skipped: translation "
                    "structure mismatch (%s); every language kept as it was.",
                    view.id,
                    company.id,
                    mismatch,
                )
                report = dict(report, skipped="translation structure mismatch")
            except Exception:
                self.env.invalidate_all()
                _logger.log(
                    logging.ERROR if mode == "migration" else logging.WARNING,
                    "Legacy homepage: could not relink view %s (company %s); "
                    "the page keeps its arch as it was.",
                    view.id,
                    company.id,
                    exc_info=True,
                )
                stat["failed"] = True
                report = dict(legacy_homepage.empty_report(), skipped="error")
            stat.update(report)
            if report["skipped"] and not stat["failed"]:
                _logger.info(
                    "Legacy homepage: view %s (company %s) skipped: %s",
                    view.id,
                    company.id,
                    report["skipped"],
                )
            stats.append(stat)
        return stats

    @api.model
    def _relink_from_authoring_copy(self, view, company):
        """The migration's transform of ``view``: keep/relink decided on the
        copy in the website's default language, applied to the base arch.

        The page was written in the website's language (Spanish); the base
        (``en_US``) copy that a ``lang=None`` write rewrites holds machine
        translations of the values, which never equal the company's. So the
        email/address/web/map decisions are taken on the authoring copy
        (website language, else ``es_ES``, else ``en_US``) and passed to the
        transform of the base arch. A line one copy has and the other lacks
        stays static and is noted.
        """
        raw = self._get_arch_db_raw(view)
        base = raw.get("en_US") or view.arch_db or ""
        lang = view.website_id.default_lang_id.code
        authoring_lang = next(
            (code for code in (lang, "es_ES", "en_US") if code and raw.get(code)),
            "en_US",
        )
        facts = company._get_microsite_live_facts()
        decisions, decided = legacy_homepage.decide_contact_kinds(
            raw.get(authoring_lang) or base, facts, company._get_microsite_live_values()
        )
        new_arch, report = legacy_homepage.relink_live_data(
            base, facts, insert_missing=True, decisions=decisions
        )
        kept = list(decided["kept_static"])
        for kind in sorted(set(report["present"]) - set(decided["present"])):
            report["notes"].append(
                f"{kind} line not in the {authoring_lang} copy: kept"
            )
            kept.append(
                {
                    "kind": kind,
                    "shown": "",
                    "live": "",
                    "reason": f"not_in_{authoring_lang}",
                }
            )
        for kind in sorted(set(decided["present"]) - set(report["present"])):
            report["notes"].append(f"{kind} line only in the {authoring_lang} copy")
        report["kept_static"] = kept
        report["notes"] = list(dict.fromkeys(decided["notes"] + report["notes"]))
        return new_arch, report

    @api.model
    def _get_arch_db_raw(self, view):
        """``{lang: arch}`` of ``view`` as stored (every language)."""
        view.flush_recordset(["arch_db"])
        self.env.cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", [view.id])
        return self.env.cr.fetchone()[0] or {}

    @api.model
    def _check_translation_terms(self, view, before, after):
        """Why the write broke a language copy, or ``""``.

        A ``lang=None`` write re-maps every other language term by term, and
        a copy whose terms do not line up with the source (a different term
        count) silently gets the English source instead. Allowed: a language
        losing the translation of a term the source lost (the static values
        that became t-calls). Anything else -- another term lost, or a source
        term appearing in a copy that did not have it -- is a mismatch.
        """
        field = view._fields["arch_db"]
        source_before = before.get("en_US") or ""
        source_after = after.get("en_US") or ""
        source_terms_after = set(field.get_trans_terms(source_after))
        removed = set(field.get_trans_terms(source_before)) - source_terms_after
        for lang, old_value in before.items():
            if lang == "en_US":
                continue
            new_value = after.get(lang) or ""
            dictionary = field.get_translation_dictionary(
                source_before, {lang: old_value}
            )
            allowed = {dictionary[term][lang] for term in removed if term in dictionary}
            old_terms = set(field.get_trans_terms(old_value))
            new_terms = set(field.get_trans_terms(new_value))
            lost = old_terms - new_terms - allowed
            gained = (new_terms - old_terms) & source_terms_after
            if lost or gained:
                return (
                    f"{lang}: {len(lost)} terms lost, {len(gained)} source terms gained"
                )
        return ""

    def _relink_after_human_edit(self, kinds):
        """Make ``kinds`` live on the legacy homepages of ``self``.

        Called after a person changed those values (company form, content
        editor, directory): from then on the page follows the company even
        where the migration kept the importer's text. Never during a module
        update or an import, and never the reason the write fails.
        """
        context = self.env.context
        if not kinds or not self or any(context.get(k) for k in BULK_CONTEXT_KEYS):
            return []
        try:
            with self.env.cr.savepoint():
                return self.sudo()._relink_legacy_homepage_live_data(
                    mode="edit", kinds=frozenset(kinds)
                )
        except Exception:
            self.env.invalidate_all()
            _logger.warning(
                "Legacy homepage: relink of %s after an edit failed for "
                "companies %s; the pages keep what they show.",
                sorted(kinds),
                self.ids,
                exc_info=True,
            )
            return []

    @api.model
    def _find_legacy_homepage_backup(self, view_id):
        """The migration's own backup of ``view_id``, or an empty recordset.

        Only an attachment created by the superuser (the migration) counts,
        and the first one: anybody who may create attachments could add a
        later one with the same name.
        """
        return (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "ir.ui.view"),
                    ("res_id", "=", view_id),
                    ("name", "=", LEGACY_BACKUP_NAME.format(view_id=view_id)),
                    ("create_uid", "=", SUPERUSER_ID),
                ],
                order="id asc",
                limit=1,
            )
        )

    @staticmethod
    def _is_valid_arch_backup(data):
        """A backup is ``{language code: arch}`` with ``en_US`` in it."""
        return (
            isinstance(data, dict)
            and isinstance(data.get("en_US"), str)
            and all(
                isinstance(lang, str)
                and re.fullmatch(r"[a-z]{2,3}(_[A-Za-z0-9@]+)?", lang)
                and isinstance(arch, str)
                for lang, arch in data.items()
            )
        )

    @api.model
    def _restore_legacy_homepage_backup(self, views):
        """Put back the arch (every language) the 19.0.2.13.0 migration saved.

        Reads ``legacy-homepage-backup-<view_id>-19.0.2.13.0.json`` attached
        to each view by the migration (``_find_legacy_homepage_backup``) and
        writes that jsonb back as it was, so the language copies return byte
        for byte; the builder-save guard is not involved (the column is
        written directly). Views without a trustworthy backup are left alone
        and logged. Returns the restored views.
        """
        restored = self.env["ir.ui.view"]
        for view in views.sudo():
            backup = self._find_legacy_homepage_backup(view.id)
            if not backup:
                _logger.warning("Legacy homepage: no backup for view %s.", view.id)
                continue
            try:
                arch_db = json.loads(backup.raw)
            except ValueError:
                arch_db = None
            if not self._is_valid_arch_backup(arch_db):
                _logger.warning(
                    "Legacy homepage: backup %s of view %s is not a "
                    "{language: arch} map; not restored.",
                    backup.id,
                    view.id,
                )
                continue
            view.flush_recordset()
            self.env.cr.execute(
                "UPDATE ir_ui_view SET arch_db = %s, write_date = now() AT TIME "
                "ZONE 'UTC', write_uid = %s WHERE id = %s",
                [json.dumps(arch_db), self.env.uid, view.id],
            )
            view.invalidate_recordset()
            restored |= view
            _logger.info("Legacy homepage: view %s restored from its backup.", view.id)
        if restored:
            clear_templates_cache_on_commit(self.env)
        return restored

    def _get_microsite_website_url(self):
        """The shop's own site as a clickable absolute URL, or ``""``.

        Merchants type ``myshop.com`` as often as they type the full URL,
        and a bare host in an href is read as a relative path -- the link
        would point back into the microsite.

        Only http(s): the value lands in an ``href`` on every page of the
        shop, so ``javascript:``/``data:`` (any case, any obfuscation) give
        ``""`` and the link is not rendered (``tools/safe_url``).
        """
        self.ensure_one()
        return safe_http_url(self.partner_id.website)

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

        A Google Maps link that is still not embeddable (a short link whose
        resolution failed when it was saved) would show the browser's
        "refused to connect" page, so it falls back to the address map: the
        iframe never shows a broken page. Non-Google URLs are embedded as
        they are; they are the administrator's responsibility.

        Returns an empty string when there is nothing to show, so the
        template hides the map block entirely.
        """
        self.ensure_one()
        custom_url = self._normalize_map_url(self.microsite_map_url)
        if custom_url and map_url_tools.is_google_maps_url(custom_url):
            if not map_url_tools.is_embeddable_map_url(custom_url):
                converted = map_url_tools.to_embeddable_map_url(custom_url)
                if map_url_tools.is_embeddable_map_url(converted):
                    custom_url = converted
                else:
                    level = logging.DEBUG
                    if self.id not in _MAP_FALLBACK_REPORTED:
                        _MAP_FALLBACK_REPORTED.add(self.id)
                        level = logging.WARNING
                    _logger.log(
                        level,
                        "Company %s: map URL %s cannot be embedded; "
                        "showing the address map instead (retried daily).",
                        self.id,
                        custom_url,
                    )
                    custom_url = ""
        if custom_url:
            return custom_url
        # Same builder as the event pages (website_map_embed), so both maps
        # stay identical.
        return self.partner_id._canarias_map_embed_url() or ""

    def _get_microsite_map_link_url(self):
        """Where "View on Google Maps" points, or ``""`` for no link.

        The link the user pasted when there is one; otherwise a Google Maps
        search for what the embedded map shows (its ``q``).
        """
        self.ensure_one()
        share_url = self._normalize_map_url(self.microsite_map_share_url)
        if share_url and map_url_tools.is_google_maps_url(share_url):
            return share_url
        embed_url = self._get_microsite_map_url()
        if not map_url_tools.is_google_maps_url(embed_url):
            return ""
        query = parse_qs(urlsplit(embed_url).query).get("q", [""])[0].strip()
        if not query:
            return ""
        return "https://www.google.com/maps/search/?api=1&query=" + quote_plus(
            query, safe=","
        )

    # ------------------------------------------------------------------
    # Map link normalisation (write time)
    # ------------------------------------------------------------------
    @api.model
    def _to_embeddable_map_url(self, url):
        """Embeddable form of any Google Maps link (see ``tools/map_url``).

        Short links are resolved over the network, once, here: this runs
        when the link is saved, never when a page is rendered.
        """
        return map_url_tools.to_embeddable_map_url(
            url, resolver=map_url_tools.resolve_short_map_url
        )

    @api.model
    def _prepare_map_url_vals(self, vals):
        """``vals`` with the pasted map link converted and the original kept.

        Leaves ``vals`` alone when it has no map link or already says what
        the share link is (the migration writes both).
        """
        if "microsite_map_url" not in vals or "microsite_map_share_url" in vals:
            return vals
        pasted = (vals["microsite_map_url"] or "").strip()
        vals = dict(vals)
        if not pasted:
            vals.update(microsite_map_url=False, microsite_map_share_url=False)
            return vals
        embed_url = self._to_embeddable_map_url(pasted)
        vals["microsite_map_url"] = embed_url
        vals["microsite_map_share_url"] = (
            pasted if map_url_tools.is_share_link(pasted) else False
        )
        return vals

    def _write_map_url_aware(self, vals):
        """``super().write`` with the map link converted (see ``create``).

        A company whose stored link (or pasted original) is exactly the value
        written keeps both fields as they are: the page content editor writes
        every field back on save, and re-saving an untouched map must neither
        resolve the short link again nor forget the original. Only when the
        stored link is embeddable, though: a short link whose resolution
        failed is retried by saving it again.
        """
        if "microsite_map_url" not in vals or "microsite_map_share_url" in vals:
            return super().write(vals)
        pasted = (vals["microsite_map_url"] or "").strip()
        unchanged = self.filtered(
            lambda c: pasted
            and map_url_tools.is_embeddable_map_url(c.microsite_map_url or "")
            and pasted
            in ((c.microsite_map_url or "").strip(), c.microsite_map_share_url)
        )
        result = True
        if unchanged:
            rest_vals = {k: v for k, v in vals.items() if k != "microsite_map_url"}
            result = super(ResCompany, unchanged).write(rest_vals)
        others = self - unchanged
        if others:
            result = super(ResCompany, others).write(self._prepare_map_url_vals(vals))
        return result

    @api.model_create_multi
    def create(self, vals_list):
        return super().create([self._prepare_map_url_vals(v) for v in vals_list])

    @api.model
    def _cron_retry_map_short_links(self, limit=MAP_RETRY_BATCH):
        """Daily: resolve again the short map links that failed on save.

        At most ``limit`` companies per run, each in its own savepoint (see
        ``_normalize_existing_map_urls``); until then their page shows the
        address map. Returns the companies healed.
        """
        candidates = self.with_context(active_test=False).search(
            [
                "|",
                ("microsite_map_url", "=ilike", "%maps.app.goo.gl%"),
                ("microsite_map_url", "=ilike", "%goo.gl/maps%"),
            ],
            order="write_date asc, id",
        )
        pending = candidates.filtered(
            lambda c: map_url_tools.is_short_map_url(
                self._normalize_map_url(c.microsite_map_url)
            )
        )[:limit]
        healed = pending._normalize_existing_map_urls()
        if pending:
            _logger.info(
                "Map short links: %d retried, %d converted.",
                len(pending),
                len(healed),
            )
        return healed

    def _normalize_existing_map_urls(self):
        """Convert the stored map links of ``self``; return the changed ones.

        Idempotent: an embeddable link converts to itself. Each company runs
        in its own savepoint, so one failure (network, constraint) leaves
        that value as it was -- the render fallback covers it -- and the
        others still go through.
        """
        changed = self.browse()
        for company in self.filtered("microsite_map_url"):
            stored = company.microsite_map_url
            try:
                with self.env.cr.savepoint():
                    embed_url = self._to_embeddable_map_url(stored)
                    if embed_url == stored:
                        continue
                    share_url = company.microsite_map_share_url or (
                        stored if map_url_tools.is_share_link(stored) else False
                    )
                    company.with_context(**{MAP_NORMALIZE_CONTEXT_KEY: True}).write(
                        {
                            "microsite_map_url": embed_url,
                            "microsite_map_share_url": share_url,
                        }
                    )
                    changed |= company
            except Exception:
                _logger.warning(
                    "Company %s: could not convert map URL %s",
                    company.id,
                    stored,
                    exc_info=True,
                )
        return changed

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
        # The legacy homepages render these live, but public pages are
        # served from a one-hour response cache keyed by page (see the
        # content editor's save); without this a change shows up to an hour
        # late. Only an actual change empties it: the cache serves every
        # site, and saving a form rewrites values that did not move.
        live_changed = _live_values_change(self, LIVE_COMPANY_FIELDS, vals)
        map_changed = _live_values_change(self, frozenset({"microsite_map_url"}), vals)
        result = self._write_map_url_aware(vals)
        if live_changed:
            clear_templates_cache_on_commit(self.env)
        if (
            map_changed
            and (vals.get("microsite_map_url") or "").strip()
            and not self.env.context.get(MAP_NORMALIZE_CONTEXT_KEY)
        ):
            # A human set the shop's own map link: it wins over the page's.
            # Only an explicit link: clearing the field must never turn a
            # page's own map into the partner-address one, and the cron that
            # converts stored links is not a human edit.
            self.filtered("microsite_map_url")._relink_after_human_edit({"map"})
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
