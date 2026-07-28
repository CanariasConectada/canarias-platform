# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
import unicodedata
from datetime import date
from urllib.parse import urlsplit

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.rating.models import rating_data

MIN_PHOTO_YEAR = 1840  # First photographs of the Canary Islands era.
# Only these schemes may reach an ``href``. Anything else (``javascript:``,
# ``data:``, ``vbscript:`` ...) is a stored-XSS vector once clicked.
ALLOWED_URL_SCHEMES = ("http", "https")


def slugify(value):
    """ASCII slug of a name, dependency-free (same rules as the legacy one)."""
    value = unicodedata.normalize("NFKD", str(value))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^\w\s-]", "", value).strip().lower()
    return re.sub(r"[-\s]+", "-", value)


class LocalContentItem(models.Model):
    """A published place, memory or any other local content entry.

    Fusion of the legacy ``memoria.viva.historia`` and
    ``lugares.interes.historia`` models: the owning module becomes the
    ``type_id`` field and every website page is parameterized by it.
    """

    _name = "website.local.content.item"
    _description = "Local Content Item"
    _inherit = ["website.published.mixin", "image.mixin"]
    _order = "create_date desc, id desc"

    # --- Identification and taxonomy -----------------------------------
    name = fields.Char(string="Title", required=True, index=True)
    slug = fields.Char(
        required=True,
        copy=False,
        index=True,
        help="URL segment of the public detail page. Generated from the "
        "title when left empty; must be unique within the content type.",
    )
    type_id = fields.Many2one(
        comodel_name="website.local.content.type",
        string="Content Type",
        required=True,
        index=True,
        ondelete="restrict",
    )
    category_id = fields.Many2one(
        comodel_name="website.local.content.category",
        string="Category",
        required=True,
        index=True,
        ondelete="restrict",
        domain="[('type_id', '=', type_id)]",
    )
    subcategory_id = fields.Many2one(
        comodel_name="website.local.content.subcategory",
        string="Subcategory",
        ondelete="restrict",
        domain="[('category_id', '=', category_id)]",
    )
    tag_ids = fields.Many2many(
        comodel_name="website.local.content.tag",
        relation="website_local_content_item_tag_rel",
        column1="item_id",
        column2="tag_id",
        string="Tags",
        help="Transversal themes of the item, independent of the "
        "category taxonomy (legacy theme level).",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    website_ids = fields.Many2many(
        comodel_name="website",
        string="Websites",
        help="Websites (microsites) where this item is visible. Empty means "
        "every website on which its content type is available, matching "
        "the per-zone scoping of the legacy modules.",
    )

    # --- Editorial content ----------------------------------------------
    description = fields.Text(
        string="Short Description",
        help="Teaser shown on the cards of the public index page.",
    )
    body = fields.Html(
        string="Full Story",
        help="Long, formatted description shown on the detail page.",
    )
    photo_year = fields.Integer(
        help="Year the photograph was taken (Living Memory style types). "
        "Enables the decade filter on the public page.",
    )
    decade = fields.Integer(
        compute="_compute_decade",
        store=True,
        help="Decade of the photograph, computed from the photo year.",
    )

    # --- Location ---------------------------------------------------------
    address = fields.Char()
    city = fields.Char()
    district = fields.Char()
    latitude = fields.Float(digits=(10, 8))
    longitude = fields.Float(digits=(11, 8))

    # --- Contact and links -------------------------------------------------
    phone = fields.Char()
    whatsapp = fields.Char()
    instagram = fields.Char()
    tiktok = fields.Char()
    external_website = fields.Char(
        help="External website of the place or business, if any.",
    )
    opening_hours = fields.Text(
        help="Free-form opening hours shown on the detail page.",
    )

    # --- Submission provenance (public form of the legacy modules) -------
    # The item model is readable by public/portal (see ir.model.access.csv),
    # so the submitter's personal data (phone, email, ID document) is gated at
    # field level to an internal group: public and portal users can never read
    # this PII over RPC even though the record itself is public. ``sudo()``
    # (the migration and any privileged write path) still bypasses the gate.
    _PII_GROUPS = "website_local_content.group_local_content_manager"
    submitter_name = fields.Char(help="Name of the person who sent the entry.")
    submitter_phone = fields.Char(groups=_PII_GROUPS)
    submitter_email = fields.Char(groups=_PII_GROUPS)
    submitter_identity = fields.Char(
        string="Submitter ID Document",
        groups=_PII_GROUPS,
        help="Identity document (DNI/NIE) collected by the legacy public "
        "submission form. Kept for the data migration.",
    )
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Submitted By",
        help="Registered contact that sent this entry, when known.",
    )
    user_id = fields.Many2one(
        comodel_name="res.users",
        string="Managed By",
        ondelete="set null",
    )

    # --- Workflow -----------------------------------------------------------
    state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("pending", "Pending Approval"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        default="draft",
        required=True,
        index=True,
        copy=False,
    )

    # --- Relations ----------------------------------------------------------
    image_ids = fields.One2many(
        comodel_name="website.local.content.image",
        inverse_name="item_id",
        string="Gallery",
    )
    like_ids = fields.One2many(
        comodel_name="website.local.content.like",
        inverse_name="item_id",
        string="Likes",
    )
    like_count = fields.Integer(compute="_compute_like_count", store=True)

    # --- Ratings (read-only display of the migrated legacy reviews) -------
    # The item does NOT inherit ``rating.mixin``: in Odoo 19 that mixin
    # extends ``mail.thread`` (chatter, followers, subtypes), a heavy
    # behavioural change this read-only display does not need. The fields
    # below mirror the mixin's stats with one ``_read_group`` per batch.
    rating_ids = fields.One2many(
        comodel_name="rating.rating",
        inverse_name="res_id",
        string="Ratings",
        groups="base.group_user",
        domain=lambda self: [("res_model", "=", self._name)],
    )
    rating_avg = fields.Float(
        string="Average Rating",
        digits=(3, 2),
        compute="_compute_rating_stats",
        compute_sudo=True,
    )
    rating_count = fields.Integer(
        string="Rating Count",
        compute="_compute_rating_stats",
        compute_sudo=True,
    )

    _slug_type_uniq = models.Constraint(
        "unique(slug, type_id)",
        "The slug must be unique within the same content type.",
    )

    # --- Constraints -------------------------------------------------------
    @api.constrains("photo_year")
    def _check_photo_year(self):
        current_year = date.today().year
        for record in self:
            if record.photo_year and not (
                MIN_PHOTO_YEAR <= record.photo_year <= current_year
            ):
                raise ValidationError(
                    _(
                        "The photo year must be between %(min_year)s and "
                        "%(max_year)s.",
                        min_year=MIN_PHOTO_YEAR,
                        max_year=current_year,
                    )
                )

    @api.constrains("latitude", "longitude")
    def _check_coordinates(self):
        for record in self:
            if record.latitude and not -90 <= record.latitude <= 90:
                raise ValidationError(_("Latitude must be between -90 and 90."))
            if record.longitude and not -180 <= record.longitude <= 180:
                raise ValidationError(_("Longitude must be between -180 and 180."))

    @api.constrains("external_website")
    def _check_external_website(self):
        """Reject explicit non-http(s) schemes on the external link.

        The value is rendered into an ``href`` on the public detail page, so
        a ``javascript:``/``data:`` URI would be stored XSS on click. A
        scheme-less value (``www.example.com``) is allowed and normalized to
        https at render time (see ``get_external_website_url``).
        """
        for record in self:
            url = (record.external_website or "").strip()
            if not url:
                continue
            scheme = urlsplit(url).scheme
            if scheme and scheme.lower() not in ALLOWED_URL_SCHEMES:
                raise ValidationError(
                    _(
                        "The external website must be an http(s) address or a "
                        "scheme-less URL; the %(scheme)s scheme is not allowed.",
                        scheme=scheme,
                    )
                )

    @api.constrains("type_id", "category_id", "subcategory_id")
    def _check_taxonomy_consistency(self):
        for record in self:
            if record.category_id.type_id != record.type_id:
                raise ValidationError(
                    _("The category does not belong to the selected content type.")
                )
            if (
                record.subcategory_id
                and record.subcategory_id.category_id != record.category_id
            ):
                raise ValidationError(
                    _("The subcategory does not belong to the selected category.")
                )

    # --- Computes ------------------------------------------------------------
    @api.depends("photo_year")
    def _compute_decade(self):
        for record in self:
            record.decade = (record.photo_year // 10) * 10 if record.photo_year else 0

    @api.depends("like_ids")
    def _compute_like_count(self):
        for record in self:
            record.like_count = len(record.like_ids)

    def _rating_domain(self):
        """Domain of the ratings that count for the public statistics.

        Same normalization as ``rating.mixin._rating_domain``: only consumed
        (filled) ratings with a real value; empty/unfilled rows never count.
        """
        return [
            ("res_model", "=", self._name),
            ("res_id", "in", self.ids),
            ("consumed", "=", True),
            ("rating", ">=", rating_data.RATING_LIMIT_MIN),
        ]

    @api.depends("rating_ids.rating", "rating_ids.consumed")
    def _compute_rating_stats(self):
        """Average and count of the consumed ratings, one query per batch."""
        groups = self.env["rating.rating"]._read_group(
            self._rating_domain(),
            ["res_id"],
            ["__count", "rating:avg"],
        )
        stats = {res_id: (count, avg) for res_id, count, avg in groups}
        for record in self:
            count, avg = stats.get(record.id, (0, 0.0))
            record.rating_count = count
            record.rating_avg = avg

    def _compute_website_url(self):
        super()._compute_website_url()
        for record in self:
            if record.id:
                record.website_url = f"/explora/{record.type_id.url_slug}/{record.slug}"

    # --- ORM overrides ---------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("slug") and vals.get("name"):
                vals["slug"] = self._generate_unique_slug(
                    vals["name"], vals.get("type_id")
                )
        return super().create(vals_list)

    def _generate_unique_slug(self, name, type_id):
        """Slug of the name, suffixed with a counter until unique per type."""
        base_slug = slugify(name) or "item"
        slug = base_slug
        counter = 1
        while (
            self.with_context(active_test=False)
            .sudo()
            .search_count([("slug", "=", slug), ("type_id", "=", type_id)], limit=1)
        ):
            slug = f"{base_slug}-{counter}"
            counter += 1
        return slug

    # --- Workflow actions ----------------------------------------------------
    def action_approve(self):
        self.write({"state": "approved", "is_published": True})

    def action_reject(self):
        self.write({"state": "rejected", "is_published": False})

    def action_reset_to_draft(self):
        self.write({"state": "draft", "is_published": False})

    def action_submit_for_approval(self):
        self.write({"state": "pending"})

    # --- Website scoping -----------------------------------------------
    @api.model
    def _get_website_visibility_domain(self, website):
        """Domain of the items visible on the given website.

        An item without websites is visible everywhere (the migrated rows
        keep their current behaviour until websites are assigned).
        """
        return [
            "|",
            ("website_ids", "=", False),
            ("website_ids", "in", website.id),
        ]

    def _is_visible_on_website(self, website):
        """Whether this item is published on the given website."""
        self.ensure_one()
        return not self.website_ids or website in self.website_ids

    # --- Public rendering helpers -----------------------------------------
    def get_image_url(self):
        """URL of the streamed public image (see the ``/img`` route)."""
        self.ensure_one()
        return f"/explora/{self.type_id.url_slug}/img/{self.id}"

    def get_external_website_url(self):
        """Safe ``href`` for the external link shown on the detail page.

        Scheme-less values (``www.example.com``) are normalized to https so
        the browser opens them as an absolute URL instead of resolving them
        as a same-site relative path. ``_check_external_website`` guarantees
        any explicit scheme is http/https, so the result is never a
        ``javascript:``/``data:`` URI.
        """
        self.ensure_one()
        url = (self.external_website or "").strip()
        if not url:
            return ""
        if not urlsplit(url).scheme:
            url = f"https://{url}"
        return url

    def get_public_ratings(self):
        """Consumed ratings shown on the public detail page, newest first.

        Returns an empty recordset when the item itself is not publicly
        visible (unpublished or not approved), so a caller can never leak
        the reviews of a hidden item.
        """
        self.ensure_one()
        rating_model = self.env["rating.rating"].sudo()
        if not self.is_published or self.state != "approved":
            return rating_model.browse()
        return rating_model.search(
            self._rating_domain(), order="write_date desc, id desc"
        )

    @api.model
    def get_rating_author_name(self, rating):
        """Public display name of a review author (anonymous fallback)."""
        return rating.partner_id.name or _("Visitor")

    def has_session_liked(self, session_key):
        """Whether the given anonymous session already liked this item."""
        self.ensure_one()
        if not session_key:
            return False
        return bool(
            self.like_ids.filtered(lambda like: like.session_key == session_key)
        )
