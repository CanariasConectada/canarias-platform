# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

# The fields a merchant is allowed to change about their own page, and the
# only ones this screen ever writes. Everything else on ``res.company`` --
# the VAT number, the currency, the accounts, the name the invoices carry --
# is somebody else's job and stays out of reach.
#
# One tuple, read by both ``default_get`` and ``action_save``, so the screen
# and the write can never come to disagree about what is editable.
CONTENT_FIELDS = (
    "microsite_name",
    "microsite_button_text",
    "microsite_hero_image",
    "microsite_intro_title",
    "microsite_intro_image",
    "microsite_banner_title",
    "microsite_banner_image",
    "microsite_opening_hours",
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
    microsite_opening_hours = fields.Char(string="Opening hours")
    microsite_delivery_info = fields.Char(string="Delivery")
    microsite_parking_info = fields.Char(string="Parking and directions")
    microsite_phone = fields.Char(string="Phone")
    microsite_phone2 = fields.Char(string="Second phone")
    microsite_map_url = fields.Char(string="Map")
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
        exactly as before. Owner of several: a picker step first, so they say
        WHICH one before the editor opens. Zone staff whose session company
        IS the zone company (absent from the picker set on purpose) still
        reach their own editor directly through the legacy singular. An
        administrator gets the shops themselves, where the very same content
        already sits on a page of the company form and where they are the
        ones allowed to write it.
        """
        Company = self.env["res.company"]
        candidates = Company._get_own_microsite_companies()
        if len(candidates) > 1:
            return {
                "type": "ir.actions.act_window",
                "name": _("Choose your shop"),
                "res_model": "microsite.company.picker",
                "view_mode": "form",
                "target": "new",
            }
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
        return values

    # ------------------------------------------------------------------
    # Saving
    # ------------------------------------------------------------------
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
        company.write(payload)
        return {"type": "ir.actions.act_window_close"}
