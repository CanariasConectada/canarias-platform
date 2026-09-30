# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class WebsiteCategoryTile(models.Model):
    """The picture ONE shop shows for a category, without touching the category.

    Asked for on 2026-09-16: "si ellos lo colocan para su sitio, esa imagen
    solo para su sitio; no quiero que modifiquen esto para todos los demás
    comercios que usan esta categoría". The 402 public categories are shared
    by every shop, and ``cover_image`` lives on the category itself, so a
    merchant who changed it would have redecorated everybody's shop. This row
    sits between the site and the category: the tile renderer of
    ``website_sale_canarias`` asks for it first and falls back to the shared
    ``cover_image`` when there is none.
    """

    _name = "website.category.tile"
    _description = "Category tile of a shop"
    # Own categories first, then the shared ones, each block alphabetical:
    # the order the merchant reads their shop in.
    _order = "category_type, category_name, id"

    website_id = fields.Many2one(
        comodel_name="website",
        string="Shop",
        required=True,
        index=True,
        ondelete="cascade",
    )
    category_id = fields.Many2one(
        comodel_name="product.public.category",
        string="Category",
        required=True,
        index=True,
        ondelete="cascade",
    )
    image = fields.Image(
        string="Image for my shop",
        max_width=1024,
        max_height=1024,
        help="Shown on the tile of this category at the top of your shop. "
        "The image only changes in your shop; the shared category stays the "
        "same for the other shops.",
    )
    name = fields.Char(
        string="Label for my shop",
        help="Optional. Replaces the category name on the tile of your shop only.",
    )
    sequence = fields.Integer(default=10)
    category_type = fields.Selection(
        selection=[("own", "Own"), ("shared", "Shared")],
        string="Type",
        compute="_compute_category_type",
        store=True,
        help="Own: a category of your shop alone. Shared: a platform category "
        "other shops use too; only its image and label change in your shop.",
    )
    # Stored for the order above, spelled in the shop's own language (a
    # stored related field of a translated name would be right in one
    # language alone). Editable on own rows: this list is the only screen
    # of the shop's categories, so an own category is renamed here, and the
    # inverse writes through the caller's own access. A shared category is
    # not the merchant's to rename: read-only in the view, refused below.
    category_name = fields.Char(
        string="Category name",
        compute="_compute_category_name",
        inverse="_inverse_category_name",
        store=True,
        readonly=False,
    )
    # The categories a row of THIS shop may point at: the ones its products
    # carry, plus the shop's own. Non-stored, so the many2one's domain in the
    # list follows the shop without a hardcoded id anywhere.
    allowed_category_ids = fields.Many2many(
        comodel_name="product.public.category",
        compute="_compute_allowed_category_ids",
        string="Categories of this shop",
    )

    _website_category_unique = models.Constraint(
        "UNIQUE (website_id, category_id)",
        "This shop already has a tile for that category.",
    )

    @api.depends("website_id")
    def _compute_allowed_category_ids(self):
        for tile in self:
            website = tile.website_id
            tile.allowed_category_ids = (
                website._wsmc_shop_category_choices() if website else False
            )

    @api.depends("category_id.website_id")
    def _compute_category_type(self):
        for tile in self:
            tile.category_type = "own" if tile.category_id.website_id else "shared"

    @api.depends("category_id.name", "website_id.default_lang_id")
    def _compute_category_name(self):
        for tile in self:
            lang = tile.website_id.default_lang_id.code
            category = (
                tile.category_id.with_context(lang=lang) if lang else tile.category_id
            )
            tile.category_name = category.name

    def _inverse_category_name(self):
        """Rename the own category of the row, as the caller.

        Not ``sudo``: the record rules and guards of
        ``product.public.category`` decide, exactly as on any other write,
        so a row of another shop's category fails there too. The name is
        written in the shop's language, the one the column shows; the
        English source follows while it still carries the same text, so a
        category never translated keeps one name everywhere.
        """
        for tile in self:
            if tile.category_id.website_id != tile.website_id or not tile.website_id:
                raise AccessError(
                    _(
                        "%(category)s is a shared category: only its image and "
                        "label can change in your shop.",
                        category=tile.category_id.display_name,
                    )
                )
            name = (tile.category_name or "").strip()
            if not name:
                raise UserError(_("A category needs a name."))
            lang = tile.website_id.default_lang_id.code or "en_US"
            category = tile.category_id
            source = category.with_context(lang="en_US").name
            shown = category.with_context(lang=lang).name
            if name == shown:
                continue
            category.with_context(lang=lang).write({"name": name})
            if lang != "en_US" and source == shown:
                category.with_context(lang="en_US").write({"name": name})

    @api.constrains("website_id", "category_id")
    def _check_category_belongs_here(self):
        """A shared category or one of this very shop, never another shop's own."""
        for tile in self:
            owner = tile.category_id.website_id
            if owner and owner != tile.website_id:
                raise ValidationError(
                    _(
                        "%(category)s belongs to another shop's site, so it "
                        "cannot be shown as a tile here.",
                        category=tile.category_id.display_name,
                    )
                )

    # ------------------------------------------------------------------
    # The screen
    # ------------------------------------------------------------------

    @api.model
    def _action_for_website(self, website):
        """The tiles of one shop, with everything a new row needs pre-set."""
        return {
            "type": "ir.actions.act_window",
            "name": _("Shop categories"),
            "res_model": self._name,
            "view_mode": "list,form",
            "domain": [("website_id", "=", website.id)],
            "help": "<p>%s</p>"
            % _(
                "All the categories of your shop are listed here: your own "
                "and the shared ones your products use. Upload an image to "
                "show it at the top of your shop. A category only appears if "
                "it has published products."
            ),
            "context": {
                "default_website_id": website.id,
                "wsmc_website_id": website.id,
            },
            "target": "current",
        }

    @api.model
    def action_open_shop_categories(self):
        """What the "Shop categories" menu opens, decided by who is asking.

        Same routing as ``microsite.content.editor.action_open_page_content``,
        which the merchants already know: a sole owner lands on their shop's
        tiles at once, an owner of several shops gets the "My shops" list
        (each row now has a Categories button), and an administrator, who
        has no shop of their own, gets every shop's tiles grouped by site.
        """
        Company = self.env["res.company"]
        candidates = Company._get_own_microsite_companies()
        if len(candidates) > 1:
            return Company._action_open_own_websites(candidates)
        company = candidates or Company._get_own_microsite_company()
        if company:
            company.website_id._wsmc_sync_category_rows()
            return self._action_for_website(company.website_id)
        if self.env.user.has_group("base.group_erp_manager"):
            return {
                "type": "ir.actions.act_window",
                "name": _("Shop categories"),
                "res_model": self._name,
                "view_mode": "list,form",
                "context": {"group_by": "website_id"},
                "target": "current",
            }
        raise UserError(
            _(
                "Your account is not linked to a shop with its own site, so "
                "there are no shop categories to curate."
            )
        )

    def _wsmc_website_from_context(self):
        """The shop the list was opened for, re-checked against the caller.

        The header buttons of the list run on no record at all; the shop
        travels in the action context, and an id in a context is a request,
        so ownership is asserted again here rather than trusted. An
        administrator's grouped list carries no shop: they get an empty
        website and the actions widen to every shop's own categories.
        """
        website_id = self.env.context.get("wsmc_website_id")
        website = self.env["website"].browse(int(website_id or 0)).exists()
        if website:
            website._pmm_assert_own_site()
            return website
        if self.env.user.has_group("base.group_erp_manager"):
            return self.env["website"]
        raise UserError(_("Open this screen from the Shop categories menu."))

    def action_new_own_category(self):
        """Add an own category to this shop, as a new row of this very list.

        It is created with a placeholder name the merchant overwrites in the
        row; the create hook of ``product.public.category`` adds the row, and
        a non-action result makes the list reload. An administrator's grouped
        list has no shop to create it on, so they get the category form.
        """
        website = self._wsmc_website_from_context()
        if website:
            self.env["product.public.category"].create(
                {"name": _("New category"), "website_id": website.id}
            )
            return True
        return {
            "type": "ir.actions.act_window",
            "name": _("New own category"),
            "res_model": "product.public.category",
            "view_mode": "form",
            "views": [
                (
                    self.env.ref(
                        "website_sale_merchant_categories."
                        "product_public_category_view_form_merchant"
                    ).id,
                    "form",
                )
            ],
            "target": "new",
        }

    def action_delete_own_category(self):
        """Delete the own category of the row; its row goes with it.

        Unlinked as the caller, so the record rules refuse another shop's
        category; a shared one is refused here first, whoever asks, because
        this screen is about one shop and a shared category belongs to all.
        The row disappears through ``ondelete="cascade"``.
        """
        self.check_access("unlink")
        for tile in self:
            if tile.category_id.website_id != tile.website_id or not tile.website_id:
                raise AccessError(
                    _(
                        "%(category)s is a shared category: it cannot be "
                        "deleted from your shop.",
                        category=tile.category_id.display_name,
                    )
                )
        self.category_id.unlink()
        return True
