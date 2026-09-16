# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..models.microsite_opening_slot import WEEKDAY_SELECTION, slot_problem_message
from ..tools.opening_hours import (
    find_slot_problem,
    format_opening_hours,
    parse_opening_hours,
    slots_from_parsed,
)

# The fields a merchant is allowed to change about their own page, and the
# only ones this screen ever writes. Everything else on ``res.company`` --
# the VAT number, the currency, the accounts, the name the invoices carry --
# is somebody else's job and stays out of reach.
#
# One tuple, read by both ``default_get`` and ``action_save``, so the screen
# and the write can never come to disagree about what is editable.
#
# ``microsite_opening_hours`` is NOT in it any more: the merchant edits the
# opening periods as rows (``opening_slot_ids``) and the text is generated
# from them on the company. See ``_load_opening_slots`` / ``_save_opening_slots``.
CONTENT_FIELDS = (
    "microsite_name",
    "microsite_button_text",
    "microsite_hero_image",
    "microsite_intro_title",
    "microsite_intro_image",
    "microsite_banner_title",
    "microsite_banner_image",
    "microsite_delivery_info",
    "microsite_parking_info",
    "microsite_phone",
    "microsite_phone2",
    "microsite_map_url",
    "microsite_about_title",
    "microsite_about_text",
    "microsite_services_title",
    "microsite_services_text",
)

# Social links are NOT part of ``CONTENT_FIELDS`` because they do not live
# (only) on the company. The footer resolves each network as "website value
# first, company value as fallback" (see ``models/website.py``), and the
# migration left the real values on the website side: 119 of 211 sites carry
# them there, and not one company does. So this screen reads them in the
# footer's own order and writes them to BOTH sides -- the website so the
# footer shows the change, the company so clearing a link actually clears it
# instead of resurrecting an older company value through the fallback.
SOCIAL_FIELDS = (
    "social_facebook",
    "social_instagram",
    "social_twitter",
    "social_youtube",
    "social_linkedin",
)

# The shop's OWN site (client request 2026-09-16: "falta un espacio en donde
# podamos colocar el website de las personas"). It is core
# ``res.company.website`` -- a related field on the partner -- so it is not
# in ``CONTENT_FIELDS`` either: it gets its own load/save because the value
# is normalised and checked before it reaches the company, and because its
# name on this screen (``company_website``) must not collide with
# ``website_url``, which is the address of the MICROSITE this screen edits.
_ALLOWED_WEBSITE_SCHEMES = ("http", "https")
# ``scheme:`` at the start of what the merchant typed -- ``javascript:``,
# ``mailto:``, ``ftp://`` -- as opposed to ``localhost:8080``, where the colon
# introduces a port. Only a value WITHOUT a scheme gets ``https://`` added.
_URL_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:(?!\d)")


class MicrositeContentEditor(models.TransientModel):
    """The merchant's own screen for the content of their page.

    WHY THIS IS NOT SIMPLY THE COMPANY FORM. The content lives on
    ``res.company``, and ``res.company`` is readable by every internal user
    and writable by ``base.group_erp_manager`` alone. Pointing a merchant at
    the company form would have produced a screen that loads and then refuses
    to save; widening the ACL so that it saves would have handed 218 shop
    owners their own VAT number, currency and chart of accounts to edit.

    So the screen is a transient of its own. It reads the shop's values in,
    and writes back exactly ``CONTENT_FIELDS`` with sudo. The company being
    written is resolved by :meth:`_resolve_target_company`, the single
    chokepoint every read and write on this screen (and its bridges in
    ``company_facilities`` and ``website_directory_partner_microsite``) goes
    through. A company id MAY now travel in the request -- an owner of
    several shops picks one -- but authorisation never does: the id is only
    ever a candidate, checked against
    ``res.company._get_editable_microsite_companies()``, and refused with
    ``AccessError`` when it is not a member. It is not a choice; it is a
    request against a set the server computed.
    """

    _name = "microsite.content.editor"
    _description = "Page content of my shop"

    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Shop",
        readonly=True,
        help="Resolved from your account. It is not a choice.",
    )
    website_url = fields.Char(
        string="Address",
        readonly=True,
        help="Where the page this screen edits can be seen.",
    )

    microsite_name = fields.Char(string="Trade name")
    microsite_button_text = fields.Char(string="Cover button")
    microsite_hero_image = fields.Image(string="Cover image")
    microsite_intro_title = fields.Char(string="Intro banner")
    microsite_intro_image = fields.Image(string="Intro banner image")
    microsite_banner_title = fields.Char(string="Closing banner")
    microsite_banner_image = fields.Image(string="Closing banner image")
    # One row per opening period; a day with a morning and an afternoon
    # shift is two rows. What the merchant asked for on 2026-09-15: "que
    # pueda introducir, por día, tantas horas de apertura y cierre como
    # necesite", instead of a notation they did not understand.
    opening_slot_ids = fields.One2many(
        comodel_name="microsite.content.editor.slot",
        inverse_name="editor_id",
        string="Opening periods",
    )
    # Read-only preview of the text the page will show, generated from the
    # rows exactly as the company will generate it on save.
    microsite_opening_hours = fields.Char(
        string="Opening hours",
        compute="_compute_microsite_opening_hours",
    )
    microsite_delivery_info = fields.Char(string="Delivery")
    microsite_parking_info = fields.Char(string="Parking and directions")
    microsite_phone = fields.Char(string="Phone")
    microsite_phone2 = fields.Char(string="Second phone")
    microsite_map_url = fields.Char(string="Map")
    social_facebook = fields.Char(string="Facebook")
    social_instagram = fields.Char(string="Instagram")
    social_twitter = fields.Char(string="X/Twitter")
    social_youtube = fields.Char(string="YouTube")
    social_linkedin = fields.Char(string="LinkedIn")
    company_website = fields.Char(
        string="Website",
        help="Your shop's own site outside this platform, shown with a globe "
        "icon next to the social links.",
    )
    microsite_about_title = fields.Char(string="Our story: heading")
    microsite_about_text = fields.Text(string="Our story")
    microsite_services_title = fields.Char(string="What we do: heading")
    microsite_services_text = fields.Text(string="What we do")

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _editable_field_names(self):
        """The whitelist, so a bridge module can add to it.

        ``company_facilities`` adds what a shop offers to this same screen;
        without a hook it would have had to reach into the constant.
        """
        return list(CONTENT_FIELDS)

    @api.model
    def _resolve_target_company(self, company_id=None):
        """The one shop THIS request may act on, or ``AccessError``.

        The id is a request, not a fact -- but a request against a set the
        server computed is a choice, not a claim. Whatever ``company_id``'s
        origin (an action context, a stored form field, nothing at all), it
        is only ever a CANDIDATE: coerced to ``int`` and checked for
        membership in ``res.company._get_editable_microsite_companies()``,
        the single authority. Anything else -- garbage, a stranger's id, an
        id that used to be valid and no longer is -- is refused with
        ``AccessError``, never a silent fallback to a different company.

        When ``company_id`` is falsy -- ``None``, ``False``, or ``0`` -- it is
        treated as "no id was given at all" and falls back to the SESSION
        company (``_get_own_microsite_company()``), exactly as every caller
        of this screen worked before a picker existed. This is deliberate:
        ``0`` is never a real ``res.company`` id (Odoo ids start at 1), so
        there is no legitimate shop it could be mistaken for, and treating it
        as "absent" rather than "invalid" keeps the contract simple -- one
        falsy value, one behaviour. That path raises ``UserError`` on
        failure, unchanged, since it is not a tampering attempt: it is simply
        "this account has no shop".
        """
        Company = self.env["res.company"]
        if not company_id:
            company = Company._get_own_microsite_company()
            if not company:
                raise UserError(
                    _(
                        "Your account is not linked to a shop with its own "
                        "site, so there is no page content to edit."
                    )
                )
            return company.sudo()
        try:
            company_id = int(company_id)
        except (TypeError, ValueError) as exc:
            raise AccessError(_("Your account is not linked to that shop.")) from exc
        company = Company._get_editable_microsite_companies().filtered(
            lambda c: c.id == company_id
        )
        if not company:
            raise AccessError(_("Your account is not linked to that shop."))
        return company.sudo()

    @api.model
    def action_open_page_content(self):
        """What the "Page content" menu opens, decided by who is asking.

        The menu is gated on ``group_website_restricted_editor``, which the
        218 merchants hold -- and so does every administrator. An
        administrator has no shop of their own, so the screen used to greet
        them with "your account is not linked to a shop": a menu entry whose
        only outcome was an error dialog.

        Sole owner of a shop: straight to the editor, zero extra clicks,
        exactly as before. Owner of several: the list of their shops, which
        is a screen they can work from -- open one, jump to its orders, its
        pages, or its content -- rather than the modal that used to stand in
        front of the editor and nothing else (reported 2026-09-14: "estamos
        limitando bastante por el modal ... mejor una vista de lista"). Zone staff whose session company
        IS the zone company (absent from the picker set on purpose) still
        reach their own editor directly through the legacy singular. An
        administrator gets the shops themselves, where the very same content
        already sits on a page of the company form and where they are the
        ones allowed to write it.
        """
        Company = self.env["res.company"]
        candidates = Company._get_own_microsite_companies()
        if len(candidates) > 1:
            return Company._action_open_own_websites(candidates)
        if len(candidates) == 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Page content"),
                "res_model": self._name,
                "view_mode": "form",
                "target": "new",
                "context": {"microsite_company_id": candidates.id},
            }
        if Company._get_own_microsite_company():
            return {
                "type": "ir.actions.act_window",
                "name": _("Page content"),
                "res_model": self._name,
                "view_mode": "form",
                "target": "new",
            }
        if self.env.user.has_group("base.group_erp_manager"):
            return {
                "type": "ir.actions.act_window",
                "name": _("Page content of the shops"),
                "res_model": "res.company",
                "view_mode": "list,form",
                # Deliberately not sudo: the list has to show what this user
                # may actually open, not a promise it cannot keep.
                "domain": [("website_id", "!=", False)],
                "context": {"create": False},
            }
        raise UserError(
            _(
                "Your account is not linked to a shop with its own site, so "
                "there is no page content to edit."
            )
        )

    @api.model
    def default_get(self, fields_list):
        """Open on the resolved shop, already filled in.

        The candidate id travels in the action context set by
        ``action_open_page_content`` (single owned shop) or by
        ``microsite.company.picker.action_open_editor`` (chosen shop).
        Absent that context -- an old cached action, a direct RPC call --
        falls back to the session company, unchanged.
        """
        values = super().default_get(fields_list)
        company = self._resolve_target_company(
            self.env.context.get("microsite_company_id")
        )
        source = company  # already sudo'd by _resolve_target_company
        values["company_id"] = company.id
        values["website_url"] = source.website_id.domain or ""
        for name in self._editable_field_names():
            field = self._fields.get(name)
            if not field:
                continue
            value = source[name]
            # Relational values have to cross as ids: a recordset read in the
            # company's environment would carry that environment with it.
            if field.type in ("many2many", "one2many"):
                values[name] = [(6, 0, value.ids)]
            elif field.type == "many2one":
                values[name] = value.id
            else:
                values[name] = value
        # Same order the footer resolves them in: website first, company as
        # the fallback. What the merchant sees here is what the page shows.
        website = source.website_id
        for name in SOCIAL_FIELDS:
            values[name] = (website and website[name]) or source[name] or False
        values["company_website"] = source.website or False
        values["opening_slot_ids"] = [
            (0, 0, {"weekday": str(weekday), "open_time": open_time, "close_time": close_time})
            for weekday, open_time, close_time in self._load_opening_slots(source)
        ]
        return values

    @api.model
    def _load_opening_slots(self, company):
        """The shop's schedule as ``[(weekday, open, close), ...]``.

        The rows when the company has them; otherwise the legacy text,
        parsed, so a shop the migration did not convert still opens on
        what its page shows rather than on an empty list. A text that does
        not parse yields no rows: the merchant types the schedule again,
        which is the point of the screen.
        """
        slots = company.microsite_opening_slot_ids
        if slots:
            return [(int(s.weekday), s.open_time, s.close_time) for s in slots]
        parsed = slots_from_parsed(parse_opening_hours(company.microsite_opening_hours))
        # A text that parses but cannot be rows (one shop closes at 01:00,
        # past midnight) opens empty as well, exactly as the migration left
        # it: the rows would be refused the moment the screen is built.
        return [] if find_slot_problem(parsed) else parsed

    @api.depends(
        "opening_slot_ids.weekday",
        "opening_slot_ids.open_time",
        "opening_slot_ids.close_time",
    )
    def _compute_microsite_opening_hours(self):
        for editor in self:
            editor.microsite_opening_hours = (
                format_opening_hours(
                    (row.weekday, row.open_time, row.close_time)
                    for row in editor.opening_slot_ids
                    if row.weekday
                )
                or False
            )

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
    def _normalize_company_website(self, value):
        """The merchant's own site as it will be stored, or ``False``.

        Merchants type ``www.myshop.com`` as often as the full URL, so a
        missing scheme becomes ``https://`` here rather than at render
        time. Anything that is not an http(s) address is refused: the value
        ends up in an ``href`` on a public page, and ``javascript:`` is not
        a website.
        """
        url = (value or "").strip()
        if not url:
            return False
        if url.startswith("//"):
            url = "https:" + url
        elif not _URL_SCHEME_RE.match(url):
            url = "https://" + url
        parts = urlsplit(url)
        if parts.scheme.lower() not in _ALLOWED_WEBSITE_SCHEMES or not parts.netloc:
            raise ValidationError(
                _(
                    "The website must be an http:// or https:// address, "
                    "for example https://www.example.com."
                )
            )
        return url

    def action_save(self):
        """Write the whitelist back to the resolved shop, and nothing else.

        Re-resolved here rather than trusted from ``self.company_id``: a
        value that came back from a browser is a request, not a fact, no
        matter which field or context carried it. The action context is
        tried first (the same one ``default_get`` used to open this very
        record); ``self.company_id`` -- itself only ever set by
        ``default_get`` from that same context -- is the fallback transport
        for when the context does not survive between opening the screen and
        saving it. Both are just candidates: ``_resolve_target_company``
        is what decides.
        """
        self.ensure_one()
        company = self._resolve_target_company(
            self.env.context.get("microsite_company_id") or self.company_id.id
        )
        payload = {}
        for name in self._editable_field_names():
            field = self._fields.get(name)
            if not field:
                continue
            value = self[name]
            if field.type in ("many2many", "one2many"):
                payload[name] = [(6, 0, value.ids)]
            elif field.type == "many2one":
                payload[name] = value.id
            else:
                payload[name] = value
        # The opening-hours constraint and the map-URL scheme check live on
        # res.company and still run here: sudo skips the access rules, never
        # the validation.
        social_payload = {name: self[name] or False for name in SOCIAL_FIELDS}
        payload["website"] = self._normalize_company_website(self.company_website)
        company.write(
            dict(payload, **social_payload, **self._save_opening_slots(company))
        )
        # The website side wins in the footer, so it has to receive the same
        # value -- including an emptied one, or the old link keeps rendering.
        if company.website_id:
            company.website_id.sudo().write(social_payload)
        # Public visitors get the homepage from a one-hour response cache
        # (``website.page._get_response``, the ``templates.cached_values``
        # container), keyed by page, not by the company it renders. Writing
        # the company does not empty it; a merchant who saved and then
        # checked their site logged out would have seen the old hours for up
        # to an hour and called it "no se modifica". ``templates`` is the
        # group that container belongs to (``registry._CACHES_BY_KEY``).
        self.env.registry.clear_cache("templates")
        return {"type": "ir.actions.act_window_close"}

    def _save_opening_slots(self, company):
        """The write values that replace the shop's schedule with the rows.

        All rows are replaced (``5`` then ``0`` commands) rather than
        diffed: the schedule is small and the merchant sees the whole of it.
        The text is deliberately NOT written here: the company generates it
        from the rows (a value in the same write would be protected from
        recompute), and deleting the last row clears it
        (``microsite.opening.slot.unlink``). A shop whose legacy text never
        became rows keeps that text when the merchant saves something else
        with an empty list: nothing is written at all, so the company is
        not even asked to regenerate a text it could not have produced.
        """
        self.ensure_one()
        if not self.opening_slot_ids and not company.microsite_opening_slot_ids:
            return {}
        return {
            "microsite_opening_slot_ids": [(5, 0, 0)]
            + [
                (
                    0,
                    0,
                    {
                        "weekday": row.weekday,
                        "open_time": row.open_time,
                        "close_time": row.close_time,
                    },
                )
                for row in self.opening_slot_ids
            ]
        }


class MicrositeContentEditorSlot(models.TransientModel):
    """One row of the editor's schedule: a weekday, opens, closes.

    A transient mirror of ``microsite.opening.slot``: the editor never lets
    a merchant touch the company's rows directly (the company is writable
    by ``base.group_erp_manager`` alone, see the editor's docstring), so the
    rows are copied in on open and written back with sudo on save.
    """

    _name = "microsite.content.editor.slot"
    _description = "Opening period of the page content editor"
    _order = "weekday, open_time, id"

    editor_id = fields.Many2one(
        comodel_name="microsite.content.editor",
        required=True,
        ondelete="cascade",
    )
    weekday = fields.Selection(WEEKDAY_SELECTION, required=True)
    open_time = fields.Float(string="Opens", required=True)
    close_time = fields.Float(string="Closes", required=True)

    @api.constrains("editor_id", "weekday", "open_time", "close_time")
    def _check_slots(self):
        """Same checks as the stored rows, so the complaint reaches the
        merchant on the screen they typed in, not as a failed save."""
        for editor in self.editor_id:
            problem = find_slot_problem(
                (row.weekday, row.open_time, row.close_time)
                for row in editor.opening_slot_ids
            )
            if problem:
                raise ValidationError(
                    slot_problem_message(self.env, self._fields["weekday"], problem)
                )
