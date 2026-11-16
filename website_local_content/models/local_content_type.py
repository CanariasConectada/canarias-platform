# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class LocalContentType(models.Model):
    """A publishable content vertical (e.g. Living Memory, Places of Interest).

    Content types are DATA, not code: the legacy ``memoria_viva`` and
    ``lugares_interes`` modules were clones of each other, so this fused
    module renders any number of verticals from the same models, controller
    and templates. Adding a new vertical only requires creating a record.
    """

    _name = "website.local.content.type"
    _description = "Local Content Type"
    _order = "sequence, name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Stable technical identifier used by data files and migrations.",
    )
    url_slug = fields.Char(
        required=True,
        help="URL segment of the public pages: /explora/<url_slug>. "
        "Lowercase letters, digits and dashes only.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    description = fields.Text(
        translate=True,
        help="Short introduction shown in the hero of the public index page.",
    )
    hero_image = fields.Image(
        max_width=1920,
        max_height=1080,
        help="Full-width photograph behind the hero of the public index "
        "page. A plain gradient is used when empty.",
    )
    hero_subtitle = fields.Char(
        translate=True,
        help="Short tagline shown under the title inside the hero. Falls "
        "back to the description when empty.",
    )
    sponsor_logo = fields.Image(
        max_width=1024,
        max_height=256,
        help="Institutional logo shown in a band at the bottom of every "
        "public page of this type (e.g. the Gobierno de Canarias mark "
        "on Living Memory). Nothing is rendered when empty.",
    )
    sponsor_name = fields.Char(
        translate=True,
        help="Accessible name of the sponsor logo (image alt text).",
    )
    use_photo_year = fields.Boolean(
        string="Use Photo Year",
        help="Items of this type carry the year of the photograph and the "
        "public page offers a filter by decade (Living Memory style).",
    )
    website_ids = fields.Many2many(
        comodel_name="website",
        string="Websites",
        help="Websites where this content type is available. "
        "Empty means every website.",
    )
    item_count = fields.Integer(compute="_compute_item_count")

    _code_uniq = models.Constraint(
        "unique(code)",
        "The technical code must be unique.",
    )
    _url_slug_uniq = models.Constraint(
        "unique(url_slug)",
        "The URL slug must be unique.",
    )

    @api.constrains("url_slug")
    def _check_url_slug(self):
        for record in self:
            if not SLUG_PATTERN.match(record.url_slug or ""):
                raise ValidationError(
                    _(
                        "Invalid URL slug '%(slug)s': use lowercase letters, "
                        "digits and dashes only.",
                        slug=record.url_slug,
                    )
                )

    def _compute_item_count(self):
        counts = dict(
            self.env["website.local.content.item"]._read_group(
                [("type_id", "in", self.ids)], ["type_id"], ["__count"]
            )
        )
        for record in self:
            record.item_count = counts.get(record, 0)

    def _is_available_on_website(self, website):
        """Whether this type is published on the given website."""
        self.ensure_one()
        return not self.website_ids or website in self.website_ids

    # --- Public rendering helpers -----------------------------------------
    def get_hero_image_url(self):
        """URL of the streamed hero image, or an empty string when unset."""
        self.ensure_one()
        if not self.hero_image:
            return ""
        return f"/explora/{self.url_slug}/type-img/hero_image"

    def get_sponsor_logo_url(self):
        """URL of the streamed sponsor logo, or an empty string when unset."""
        self.ensure_one()
        if not self.sponsor_logo:
            return ""
        return f"/explora/{self.url_slug}/type-img/sponsor_logo"
