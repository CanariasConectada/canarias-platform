# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

# Zone values are kept as plain data: the legacy zone cluster is retired and
# its replacement is not decided yet. See readme/ROADMAP.md.
ZONE_SELECTION = [
    ("canarias", "Canarias Conectada"),
    ("guanarteme", "Guanarteme"),
    ("tamaraceite", "Tamaraceite"),
    ("lomolosfrailes", "Lomo los Frailes"),
]

# Alternative spellings of the same zone still present in migrated rows.
ZONE_ALIASES = {
    "lomolosfrailes": ["lomolosfrailes", "lomo_los_frailes", "lomo los frailes"],
}


class WebsiteDirectoryEntry(models.Model):
    _name = "website.directory.entry"
    _description = "Website Directory Entry"
    _inherit = ["website.published.mixin", "image.mixin"]
    _order = "sequence, name"

    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    active = fields.Boolean(
        default=True,
        help="Inactive entries are hidden from the public directory. "
        "This flag is kept in sync with the company "
        "'Show in Directory' checkbox.",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        required=True,
        index=True,
        ondelete="cascade",
    )
    category_id = fields.Many2one(
        related="company_id.category_id",
        store=True,
        readonly=True,
        index=True,
        help="Business category, taken from the company. "
        "Edit it on the company form.",
    )
    zone = fields.Selection(
        selection=ZONE_SELECTION,
        required=True,
        default="canarias",
        help="Commercial zone of the business. Kept as historical data until "
        "the new zone module lands (see the module roadmap).",
    )
    description = fields.Text(translate=True)
    short_description = fields.Char(translate=True)
    phone = fields.Char()
    email = fields.Char()
    street = fields.Char()
    city = fields.Char()
    vat = fields.Char(string="VAT")
    # Deliberately overrides the computed field of website.published.mixin:
    # the entry links to the external microsite of the business, not to an
    # internal page. Redefining the field WITHOUT a compute is not enough
    # (the mixin compute attribute is inherited and keeps overwriting the
    # value with '#'), so the compute method itself is overridden below to
    # read the URL from the company data.
    website_url = fields.Char(
        string="Website URL",
        compute="_compute_website_url",
        help="External microsite or website of the business, taken from the "
        "company (microsite modules > partner website > website domain).",
    )

    # Partial unique index: at most ONE active entry per company, while
    # archived duplicates remain allowed. Enforced at database level (the
    # index always fires before any Python constraint could) and translated
    # into the message below by the standard Odoo error mapping.
    _company_id_active_uniq = models.UniqueIndex(
        "(company_id) WHERE active IS TRUE",
        "This company already has an active directory entry.",
    )

    @api.depends(
        "company_id.partner_id.website",
        "company_id.website_id.domain",
    )
    def _compute_website_url(self):
        """Point the card link to the external site of the business.

        Overrides ``website.published.mixin`` (which would always leave
        '#'): the URL comes from the company through
        :meth:`res.company._get_directory_website_url` (extension hook >
        partner website > website domain), so the value shown on the card
        always follows the current company/partner data.
        """
        super()._compute_website_url()
        for record in self:
            if record.company_id:
                record.website_url = (
                    record.company_id._get_directory_website_url() or "#"
                )

    def get_image_url(self):
        """URL of the public image route (entry image or company logo)."""
        self.ensure_one()
        return f"/comercio/img/{self.id}"

    def get_website_url(self):
        """External URL of the business, always with a scheme."""
        self.ensure_one()
        if not self.has_external_website():
            return "#"
        if self.website_url.startswith(("http://", "https://")):
            return self.website_url
        return f"https://{self.website_url}"

    def has_external_website(self):
        """Whether the business has a real external URL (templates use it
        to hide the 'Visit' button instead of linking to '#')."""
        self.ensure_one()
        return bool(self.website_url and self.website_url != "#")

    def get_display_name(self):
        """Public name: trade name > partner name > entry name.

        ``comercial`` (trade name) belongs to l10n_es, which is NOT a
        dependency of this module, hence the defensive ``getattr``.
        """
        self.ensure_one()
        partner = self.company_id.partner_id
        if partner:
            return getattr(partner, "comercial", False) or partner.name or self.name
        return self.name

    def get_zone_label(self):
        """Human label of the zone, resilient to legacy spellings."""
        self.ensure_one()
        labels = dict(self._fields["zone"]._description_selection(self.env))
        zone = self.zone
        for canonical, aliases in ZONE_ALIASES.items():
            if zone in aliases:
                zone = canonical
                break
        return labels.get(zone, zone or "")

    def get_category_badges(self):
        """Hierarchy chain of the company category, root first.

        Returns a list of dicts (``id``, ``name``, ``level``) ready to be
        rendered as linked badges by the directory templates.
        """
        self.ensure_one()
        chain = []
        category = self.category_id
        while category:
            chain.insert(0, category)
            category = category.parent_id
        return [
            {"id": category.id, "name": category.name, "level": level}
            for level, category in enumerate(chain, start=1)
        ]
