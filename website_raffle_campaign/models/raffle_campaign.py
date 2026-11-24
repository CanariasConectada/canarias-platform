# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import io
import re
import secrets
from datetime import date, datetime

import pytz
from markupsafe import Markup, escape
from psycopg2 import IntegrityError, errors

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext

CANARY_TZ = pytz.timezone("Atlantic/Canary")

SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
PATH_RE = re.compile(r"^/[a-z0-9_-]+(?:/[a-z0-9_-]+)*$")
# First segments no campaign may take over, whatever the owner types.
RESERVED_SEGMENTS = {
    "web",
    "odoo",
    "shop",
    "sorteo",
    "website",
    "my",
    "blog",
    "event",
    "mail",
    "report",
    "static",
    "jsonrpc",
    "xmlrpc",
    "longpolling",
    "websocket",
    "contactus",
    "page",
    "forum",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_SIDE = 2000
HEIC_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"}
MAX_IMAGE_PIXELS = 40_000_000
EMAIL_LIMIT_PER_CAMPAIGN = 20


class RaffleCampaign(models.Model):
    _name = "raffle.campaign"
    _description = "Raffle Campaign"
    _inherit = ["mail.thread", "auto.translate.mixin"]
    _order = "date_start desc, id desc"

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    name = fields.Char(required=True, translate=True, tracking=True)
    active = fields.Boolean(default=True)
    website_id = fields.Many2one(
        "website", required=True, ondelete="restrict", index=True, tracking=True
    )
    slug = fields.Char(
        required=True,
        copy=False,
        help="Canonical page: /sorteo/<slug>. Lowercase letters, digits and dashes.",
    )
    short_path = fields.Char(
        copy=False,
        index=True,
        help="Short public address served in place, e.g. /ticketaso.",
    )
    alias_paths = fields.Char(
        copy=False,
        help="Comma-separated extra addresses that redirect to the short path, "
        "e.g. /ticketazo,/tiquetaso (common misspellings).",
    )
    public_url = fields.Char(compute="_compute_public_url")

    # ------------------------------------------------------------------
    # Dates and rules
    # ------------------------------------------------------------------
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    draw_date = fields.Date(help="Shown on the page; the draw itself is manual.")
    currency_id = fields.Many2one(
        "res.currency",
        required=True,
        default=lambda self: self.env.company.currency_id,
    )
    min_amount = fields.Monetary(
        currency_field="currency_id",
        required=True,
        default=15.0,
        help="A purchase counts only when its amount is STRICTLY greater.",
    )
    participating_company_ids = fields.Many2many(
        "res.company",
        "raffle_campaign_company_rel",
        "campaign_id",
        "company_id",
        string="Participating merchants",
    )
    zone_to_add = fields.Selection(
        selection="_zone_selection",
        string="Zone",
        copy=False,
        help="Only a helper: pick a zone and press the button to add its merchants.",
    )

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------
    banner_image = fields.Image(max_width=1920, max_height=1920)
    banner_button_label = fields.Char(translate=True, default="Participa")
    intro_html = fields.Html(translate=True, sanitize=True)
    # Legal text: never machine-translated (translate=False is the default).
    terms_html = fields.Html(sanitize=True)
    success_message = fields.Html(translate=True, sanitize=True)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("open", "Open"),
            ("closed", "Closed"),
            ("drawn", "Drawn"),
        ],
        default="draft",
        required=True,
        tracking=True,
        copy=False,
    )
    alternate_count = fields.Integer(default=3)
    entry_ids = fields.One2many("raffle.entry", "campaign_id")
    winner_entry_id = fields.Many2one("raffle.entry", copy=False, readonly=True)
    alternate_entry_ids = fields.One2many(
        "raffle.entry",
        compute="_compute_alternate_entry_ids",
        string="Alternates",
    )
    drawn_by = fields.Many2one("res.users", copy=False, readonly=True)
    drawn_at = fields.Datetime(copy=False, readonly=True)
    draw_candidates_snapshot = fields.Text(
        copy=False,
        readonly=True,
        help="Sorted references of the valid entries the draw picked from.",
    )
    draw_candidates_hash = fields.Char(
        copy=False, readonly=True, help="SHA-256 of the candidate snapshot."
    )
    entry_count = fields.Integer(compute="_compute_counts")
    valid_count = fields.Integer(compute="_compute_counts")
    pending_count = fields.Integer(compute="_compute_counts")

    _slug_website_unique = models.Constraint(
        "UNIQUE (website_id, slug)",
        "That address is already used by another campaign on this website.",
    )

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.model
    def _zone_selection(self):
        field = self.env["res.company"]._fields.get("commercial_zone")
        return field._description_selection(self.env) if field else []

    @api.depends("website_id", "short_path", "slug")
    def _compute_public_url(self):
        for campaign in self:
            if campaign.website_id and campaign.slug:
                base = campaign.website_id.get_base_url()
                campaign.public_url = base + (
                    campaign.short_path or f"/sorteo/{campaign.slug}"
                )
            else:
                campaign.public_url = False

    @api.depends("entry_ids.state")
    def _compute_counts(self):
        groups = self.env["raffle.entry"]._read_group(
            [("campaign_id", "in", self.ids)],
            ["campaign_id", "state"],
            ["__count"],
        )
        data = {}
        for campaign, state, count in groups:
            data.setdefault(campaign.id, {})[state] = count
        for campaign in self:
            counts = data.get(campaign.id, {})
            campaign.entry_count = sum(counts.values())
            campaign.valid_count = counts.get("valid", 0)
            campaign.pending_count = counts.get("pending", 0)

    @api.depends("entry_ids.draw_rank")
    def _compute_alternate_entry_ids(self):
        for campaign in self:
            campaign.alternate_entry_ids = campaign.entry_ids.filtered(
                lambda e: e.draw_rank > 1
            ).sorted("draw_rank")

    # ------------------------------------------------------------------
    # Validation and normalisation
    # ------------------------------------------------------------------
    @api.model
    def _normalize_vals(self, vals):
        vals = dict(vals)
        if vals.get("slug"):
            vals["slug"] = vals["slug"].strip().lower()
        if "short_path" in vals:
            vals["short_path"] = self._normalize_path(vals["short_path"])
        if "alias_paths" in vals:
            paths = [
                self._normalize_path(p) for p in (vals["alias_paths"] or "").split(",")
            ]
            vals["alias_paths"] = ",".join(p for p in paths if p) or False
        return vals

    @staticmethod
    def _normalize_path(path):
        path = (path or "").strip().lower().rstrip("/")
        return path or False

    def _alias_list(self):
        self.ensure_one()
        return [p for p in (self.alias_paths or "").split(",") if p]

    @api.constrains("slug", "short_path", "alias_paths", "website_id")
    def _check_addresses(self):
        routing_rules = None
        for campaign in self:
            if not SLUG_RE.match(campaign.slug or ""):
                raise ValidationError(
                    _("The slug may only hold lowercase letters, digits and dashes.")
                )
            paths = []
            if campaign.short_path:
                paths.append(campaign.short_path)
            paths += campaign._alias_list()
            if len(set(paths)) != len(paths):
                raise ValidationError(_("The short path and aliases must differ."))
            for path in paths:
                if not PATH_RE.match(path):
                    raise ValidationError(
                        _(
                            "'%s' is not a valid path: use /lowercase-words "
                            "without spaces or accents.",
                            path,
                        )
                    )
                if path.split("/")[1] in RESERVED_SEGMENTS:
                    raise ValidationError(_("'%s' is a reserved address.", path))
                if routing_rules is None:
                    routing_rules = {
                        rule.rule.rstrip("/")
                        for rule in self.env["ir.http"].routing_map().iter_rules()
                    }
                if path in routing_rules:
                    raise ValidationError(
                        _("'%s' is already served by Odoo; pick another.", path)
                    )
                clash = self.search(
                    [
                        ("id", "!=", campaign.id),
                        ("website_id", "=", campaign.website_id.id),
                        "|",
                        ("short_path", "=", path),
                        ("alias_paths", "ilike", path),
                    ]
                ).filtered(
                    lambda other, path=path: path
                    in ([other.short_path] + other._alias_list())
                )
                if clash:
                    raise ValidationError(
                        _("'%s' is already used by another campaign.", path)
                    )
                campaign._check_path_free(path)

    def _check_path_free(self, path):
        """Refuse a path another redirect or a website page already owns."""
        self.ensure_one()
        sites = [False, self.website_id.id]
        rewrite = (
            self.env["website.rewrite"]
            .sudo()
            .with_context(active_test=False)
            .search_count(
                [
                    ("url_from", "=", path),
                    ("website_id", "in", sites),
                    ("name", "not like", f"raffle.campaign:{self.id}:%"),
                ]
            )
        )
        page = (
            self.env["website.page"]
            .sudo()
            .search_count([("url", "=", path), ("website_id", "in", sites)])
        )
        if rewrite or page:
            raise ValidationError(
                _("'%s' is already taken by a redirect or a website page.", path)
            )

    @api.constrains("date_start", "date_end", "min_amount", "alternate_count")
    def _check_rules(self):
        for campaign in self:
            if campaign.date_end < campaign.date_start:
                raise ValidationError(_("The end date is before the start date."))
            if campaign.min_amount < 0:
                raise ValidationError(_("The minimum amount cannot be negative."))
            if campaign.alternate_count < 0:
                raise ValidationError(_("The alternate count cannot be negative."))

    # ------------------------------------------------------------------
    # ORM
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        campaigns = super().create([self._normalize_vals(v) for v in vals_list])
        campaigns._sync_rewrites()
        return campaigns

    def write(self, vals):
        result = super().write(self._normalize_vals(vals))
        if {"short_path", "alias_paths", "website_id", "active", "name"} & set(vals):
            self._sync_rewrites()
        return result

    def unlink(self):
        self._drop_rewrites()
        return super().unlink()

    def _auto_translate_fields(self):
        return ["name", "banner_button_label", "intro_html", "success_message"]

    # ------------------------------------------------------------------
    # Redirects: aliases -> short path (stock website.rewrite, 301)
    # ------------------------------------------------------------------
    def _rewrite_name(self, alias=""):
        return f"raffle.campaign:{self.id}:{alias}"

    def _drop_rewrites(self):
        rewrite = self.env["website.rewrite"].sudo().with_context(active_test=False)
        for campaign in self:
            rewrite.search([("name", "=like", campaign._rewrite_name() + "%")]).unlink()

    def _sync_rewrites(self):
        rewrite_model = (
            self.env["website.rewrite"].sudo().with_context(active_test=False)
        )
        for campaign in self:
            wanted = {}
            if campaign.short_path:
                wanted = {
                    alias: campaign.short_path for alias in campaign._alias_list()
                }
            existing = rewrite_model.search(
                [("name", "=like", campaign._rewrite_name() + "%")]
            )
            by_from = {}
            for rewrite in existing:
                if rewrite.url_from in wanted and rewrite.url_from not in by_from:
                    by_from[rewrite.url_from] = rewrite
                else:
                    rewrite.unlink()
            for alias, target in wanted.items():
                vals = {
                    "name": campaign._rewrite_name(alias),
                    "website_id": campaign.website_id.id,
                    "url_from": alias,
                    "url_to": target,
                    "redirect_type": "301",
                    "active": campaign.active,
                }
                if alias in by_from:
                    by_from[alias].write(vals)
                else:
                    rewrite_model.create(vals)

    # ------------------------------------------------------------------
    # Open / closed logic
    # ------------------------------------------------------------------
    @api.model
    def _raffle_today(self):
        """Today in the Canary Islands, whatever the server timezone."""
        return datetime.now(CANARY_TZ).date()

    def _is_open(self):
        self.ensure_one()
        today = self._raffle_today()
        return (
            self.active
            and self.state == "open"
            and self.date_start <= today <= self.date_end
        )

    def _public_phase(self):
        """What the public should see: ``soon``, ``open`` or ``ended``.

        A draft, or an open campaign whose first day has not come, is
        ``soon``; anything closed, drawn or past its last day is ``ended``.
        """
        self.ensure_one()
        if self.state == "draft":
            return "soon"
        if self.state == "open":
            today = self._raffle_today()
            if today < self.date_start:
                return "soon"
            if today <= self.date_end:
                return "open"
        return "ended"

    @api.model
    def _open_campaign(self, website):
        today = self._raffle_today()
        return self.sudo().search(
            [
                ("website_id", "=", website.id),
                ("state", "=", "open"),
                ("date_start", "<=", today),
                ("date_end", ">=", today),
            ],
            order="date_start desc, id desc",
            limit=1,
        )

    # ------------------------------------------------------------------
    # State buttons
    # ------------------------------------------------------------------
    def action_open(self):
        for campaign in self:
            if campaign.state != "draft":
                raise UserError(_("Only a draft campaign can be opened."))
            if not campaign.participating_company_ids:
                raise UserError(_("Add at least one participating merchant first."))
            if not (
                campaign.terms_html and html2plaintext(campaign.terms_html).strip()
            ):
                raise UserError(_("Write the legal terms before opening."))
        self.write({"state": "open"})

    def action_close(self):
        if any(c.state != "open" for c in self):
            raise UserError(_("Only an open campaign can be closed."))
        self.write({"state": "closed"})

    def action_reopen(self):
        if any(c.state != "closed" for c in self):
            raise UserError(_("Only a closed campaign can be re-opened."))
        self.write({"state": "open"})

    def action_set_draft(self):
        if any(c.state not in ("open", "closed") for c in self):
            raise UserError(_("Only an open or closed campaign can go back to draft."))
        self.write({"state": "draft"})

    def action_add_zone_merchants(self):
        self.ensure_one()
        if "commercial_zone" not in self.env["res.company"]._fields:
            raise UserError(_("Install the company zones module to use this helper."))
        if not self.zone_to_add:
            raise UserError(_("Pick a zone first."))
        companies = (
            self.env["res.company"]
            .sudo()
            .search([("commercial_zone", "=", self.zone_to_add)])
        )
        # The company behind the website itself is the zone's own account, not
        # a merchant a shopper can have bought from.
        companies -= self.website_id.company_id
        self.participating_company_ids = [(4, c.id) for c in companies]
        self.message_post(
            body=_(
                "%(count)s merchants of zone %(zone)s added.",
                count=len(companies),
                zone=dict(self._zone_selection()).get(self.zone_to_add),
            )
        )
        return True

    def action_download_qr(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_url",
            "url": f"/raffle/qr/{self.id}",
            "target": "self",
        }

    def _qr_png(self):
        import qrcode

        self.ensure_one()
        image = qrcode.make(self.public_url, box_size=12, border=4)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # The draw
    # ------------------------------------------------------------------
    def _terms_version(self):
        self.ensure_one()
        text = html2plaintext(self.terms_html or "")
        return hashlib.sha256(text.encode()).hexdigest()[:16]

    def _lock_for_draw(self):
        """Serialise draw / reset / anonymize on this campaign."""
        self.ensure_one()
        self.env.cr.execute(
            "SELECT id FROM raffle_campaign WHERE id = %s FOR UPDATE NOWAIT",
            [self.id],
        )
        self.invalidate_recordset()

    def action_draw(self):
        self.ensure_one()
        try:
            with self.env.cr.savepoint():
                self._lock_for_draw()
        except errors.LockNotAvailable:
            raise UserError(
                _("Another draw operation is running on this campaign. Try again.")
            ) from None
        if self.state != "closed":
            raise UserError(_("Close the campaign before drawing."))
        # A previous reset leaves no rank behind; clear defensively anyway.
        self.entry_ids.write({"draw_rank": 0})
        candidates = self.entry_ids.filtered(
            lambda e: e.state == "valid" and not e.anonymized
        )
        if not candidates:
            raise UserError(_("There are no valid entries to draw from."))
        snapshot = "\n".join(sorted(candidates.mapped("reference")))
        picks = secrets.SystemRandom().sample(
            candidates.ids, k=min(len(candidates), 1 + self.alternate_count)
        )
        items = []
        for rank, entry_id in enumerate(picks, start=1):
            entry = self.env["raffle.entry"].browse(entry_id)
            entry.draw_rank = rank
            label = _("Winner") if rank == 1 else _("Alternate %s", rank - 1)
            items.append(Markup("<li><b>%s</b>: %s</li>") % (label, entry.reference))
        self.write(
            {
                "winner_entry_id": picks[0],
                "drawn_by": self.env.user.id,
                "drawn_at": fields.Datetime.now(),
                "state": "drawn",
                "draw_candidates_snapshot": snapshot,
                "draw_candidates_hash": hashlib.sha256(snapshot.encode()).hexdigest(),
            }
        )
        # References only: the chatter must not hold personal data.
        self.message_post(
            body=Markup("%s<ul>%s</ul>")
            % (
                escape(
                    _(
                        "Draw performed among %(count)s valid entries by %(user)s.",
                        count=len(candidates),
                        user=self.env.user.name,
                    )
                ),
                Markup("").join(items),
            )
        )
        return True

    def action_reset_draw(self):
        self.ensure_one()
        self._lock_for_draw()
        if self.state != "drawn":
            raise UserError(_("There is no draw to reset."))
        if self.entry_ids.filtered("anonymized"):
            raise UserError(
                _("The entries were already anonymized: the draw cannot be repeated.")
            )
        previous = self.winner_entry_id.reference
        self.entry_ids.write({"draw_rank": 0})
        self.write(
            {
                "winner_entry_id": False,
                "drawn_by": False,
                "drawn_at": False,
                "draw_candidates_snapshot": False,
                "draw_candidates_hash": False,
                "state": "closed",
            }
        )
        self.message_post(
            body=_(
                "Draw RESET by %(user)s (previous winner: %(ref)s).",
                user=self.env.user.name,
                ref=previous,
            )
        )
        return True

    def action_anonymize_entries(self):
        """GDPR retention: keep only what the prize needs.

        Wipes personal data and receipt files of every entry except the
        winner and the alternates.
        """
        self.ensure_one()
        if self.state != "drawn":
            raise UserError(_("Anonymize only after the draw."))
        losers = self.entry_ids.filtered(lambda e: not e.draw_rank and not e.anonymized)
        losers._anonymize()
        self.message_post(
            body=_(
                "%(count)s entries anonymized by %(user)s.",
                count=len(losers),
                user=self.env.user.name,
            )
        )
        return True

    def action_anonymize_all(self):
        """For after the prize is delivered: the winner and alternates go too."""
        self.ensure_one()
        if self.state != "drawn":
            raise UserError(_("Anonymize only after the draw."))
        entries = self.entry_ids.filtered(lambda e: not e.anonymized)
        entries._anonymize()
        self.message_post(
            body=_(
                "ALL %(count)s remaining entries anonymized (winner and alternates "
                "included) by %(user)s.",
                count=len(entries),
                user=self.env.user.name,
            )
        )
        return True

    # ------------------------------------------------------------------
    # Public submission (called by the controller with sudo)
    # ------------------------------------------------------------------
    def _submit_entry(self, data, upload, ip):
        """Validate everything the form sent and create the entry.

        ``data`` holds the raw strings, ``upload`` is ``(filename, bytes)`` or
        ``None``. Raises ``UserError`` with a message in Spanish, meant for the
        shopper. Nothing is trusted: the controller does no checking itself.
        """
        self.ensure_one()
        campaign = self.sudo()
        if (data.get("honeypot") or "").strip():
            raise UserError(_("No se ha podido registrar la participación."))
        if not campaign._is_open():
            raise UserError(_("La participación no está abierta en este momento."))
        name, email, phone = campaign._clean_contact(data)
        merchant, amount, purchase_date = campaign._clean_purchase(data)
        if not data.get("is_adult"):
            raise UserError(_("Debes ser mayor de 18 años para participar."))
        if not data.get("terms_accepted"):
            raise UserError(_("Debes aceptar las bases legales para participar."))
        # Cheap checks first (size, magic bytes, counters); decoding last.
        content, mimetype, checksum = campaign._read_upload(upload)
        campaign._check_limits(email, checksum)
        stored_bytes = campaign._reencode(content, mimetype)
        entry_model = (
            self.env["raffle.entry"]
            .sudo()
            .with_context(mail_create_nosubscribe=True, mail_create_nolog=True)
        )
        vals = {
            "campaign_id": campaign.id,
            "participant_name": name,
            "email": email,
            "phone": phone,
            "merchant_id": merchant.id,
            "purchase_date": purchase_date,
            "amount": amount,
            "receipt_checksum": checksum,
            "is_adult": True,
            "terms_accepted": True,
            "terms_accepted_at": fields.Datetime.now(),
            "terms_version": campaign._terms_version(),
            "submit_ip": ip or False,
        }
        try:
            with self.env.cr.savepoint():
                entry = entry_model.create(vals)
        except IntegrityError:
            # Two uploads of the same receipt raced past the check above.
            raise UserError(_("Este ticket ya está registrado.")) from None
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .create(
                {
                    "name": f"{entry.reference}.{self._extension(mimetype)}",
                    "raw": stored_bytes,
                    "mimetype": mimetype,
                    "res_model": "raffle.entry",
                    "res_id": entry.id,
                    "public": False,
                }
            )
        )
        entry.receipt_attachment_id = attachment
        return entry

    def _clean_contact(self, data):
        name = (data.get("participant_name") or "").strip()
        if not name or len(name) > 120:
            raise UserError(_("Indica tu nombre y apellidos."))
        email = (data.get("email") or "").strip().lower()
        if not EMAIL_RE.match(email) or len(email) > 254:
            raise UserError(_("El correo electrónico no es válido."))
        phone = (data.get("phone") or "").strip()[:30]
        digits = re.sub(r"[\s().+-]", "", phone)
        if not digits.isdigit() or not 9 <= len(digits) <= 15:
            raise UserError(_("El teléfono debe tener entre 9 y 15 cifras."))
        return name, email, phone

    def _clean_purchase(self, data):
        try:
            merchant_id = int(data.get("merchant_id") or 0)
        except ValueError:
            merchant_id = 0
        merchant = self.participating_company_ids.filtered(
            lambda c: c.id == merchant_id
        )
        if not merchant:
            raise UserError(_("Elige un comercio de la lista."))
        amount = self._parse_amount(data.get("amount"))
        if amount is None or amount > 100000:
            raise UserError(_("El importe no es válido."))
        if amount <= self.min_amount:
            raise UserError(
                _(
                    "La compra debe superar los %s €.",
                    f"{self.min_amount:g}".replace(".", ","),
                )
            )
        try:
            purchase_date = date.fromisoformat((data.get("purchase_date") or "")[:10])
        except ValueError:
            raise UserError(_("La fecha de compra no es válida.")) from None
        if purchase_date > self._raffle_today():
            raise UserError(_("La fecha de compra no puede ser futura."))
        if not self.date_start <= purchase_date <= self.date_end:
            raise UserError(
                _(
                    "La compra debe haberse hecho entre el %(start)s y el %(end)s.",
                    start=self.date_start.strftime("%d/%m/%Y"),
                    end=self.date_end.strftime("%d/%m/%Y"),
                )
            )
        return merchant, amount, purchase_date

    def _check_limits(self, email, checksum):
        """Counters that are safe to enforce here.

        There is deliberately NO per-IP limit: behind nginx and Traefik every
        request reaches Odoo from the proxy address, so an IP counter would be
        global and lock every shopper out. Per-IP throttling is nginx's job
        (see ``docs/.../nginx_snippet.conf``); ``submit_ip`` is audit only.
        """
        entry_model = self.env["raffle.entry"].sudo()
        by_email = entry_model.search_count(
            [("campaign_id", "=", self.id), ("email", "=", email)]
        )
        if by_email >= EMAIL_LIMIT_PER_CAMPAIGN:
            raise UserError(
                _("Has alcanzado el máximo de participaciones con este correo.")
            )
        if entry_model.search_count(
            [("campaign_id", "=", self.id), ("receipt_checksum", "=", checksum)]
        ):
            raise UserError(_("Este ticket ya está registrado."))

    @staticmethod
    def _extension(mimetype):
        return {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/heic": "heic",
            "application/pdf": "pdf",
        }[mimetype]

    @staticmethod
    def _parse_amount(raw):
        """Accept 1.500,50 / 15,5 / 15.50 / 1.500 / 1500; ``None`` otherwise."""
        raw = (raw or "").strip().replace("€", "").replace(" ", "")
        if not raw:
            return None
        if "," in raw:
            raw = raw.replace(".", "").replace(",", ".")
        elif re.match(r"^\d{1,3}(\.\d{3})+$", raw):
            raw = raw.replace(".", "")
        if not re.match(r"^\d+(\.\d{1,2})?$", raw):
            return None
        return round(float(raw), 2)

    @staticmethod
    def _sniff(content):
        """Mimetype from the magic bytes; the filename is never consulted."""
        if content.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if content.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
            return "image/webp"
        if content[4:8] == b"ftyp" and content[8:12] in HEIC_BRANDS:
            return "image/heic"
        if content.startswith(b"%PDF-"):
            return "application/pdf"
        return None

    def _read_upload(self, upload):
        """Size and magic-byte checks only: ``(bytes, mimetype, sha256)``."""
        if not upload or not upload[1]:
            raise UserError(_("Adjunta una foto de tu ticket."))
        content = upload[1]
        if len(content) > MAX_UPLOAD_BYTES:
            raise UserError(_("El archivo es demasiado grande (máximo 10 MB)."))
        mimetype = self._sniff(content)
        if not mimetype:
            raise UserError(
                _("Formato no admitido. Sube una foto JPG, PNG, WEBP, HEIC o un PDF.")
            )
        return content, mimetype, hashlib.sha256(content).hexdigest()

    @staticmethod
    def _reencode(content, mimetype):
        """Re-encode every JPEG/PNG/WEBP: drops EXIF/GPS, caps the side.

        PDF and HEIC are stored as they came. The pixel count is checked from
        the header BEFORE decoding, so a decompression bomb costs nothing.
        """
        if mimetype not in ("image/jpeg", "image/png", "image/webp"):
            return content
        from PIL import Image, ImageOps

        bad = UserError(_("No se ha podido leer la imagen del ticket."))
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise UserError(_("La imagen es demasiado grande."))
                image.load()
                image = ImageOps.exif_transpose(image)
                image.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
                fmt = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
                if fmt[mimetype] == "JPEG" and image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                out = io.BytesIO()
                # No exif=/pnginfo= argument: nothing of the original metadata
                # survives the save.
                image.save(out, format=fmt[mimetype], quality=88)
                return out.getvalue()
        except UserError:
            raise
        except (Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise UserError(_("La imagen es demasiado grande.")) from None
        except Exception:  # noqa: BLE001 - any decoder failure means a bad file
            raise bad from None
