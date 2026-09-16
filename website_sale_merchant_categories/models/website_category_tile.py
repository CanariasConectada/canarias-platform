# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


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
    _order = "sequence, id"

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
        """The form of a category that will belong to this shop alone."""
        website = self._wsmc_website_from_context()
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
            "context": {"default_website_id": website.id} if website else {},
        }

    def action_own_categories(self):
        """Every category that belongs to this shop alone."""
        website = self._wsmc_website_from_context()
        return {
            "type": "ir.actions.act_window",
            "name": _("Own categories"),
            "res_model": "product.public.category",
            "view_mode": "list,form",
            "views": [
                (
                    self.env.ref(
                        "website_sale_merchant_categories."
                        "product_public_category_view_list_merchant"
                    ).id,
                    "list",
                ),
                (
                    self.env.ref(
                        "website_sale_merchant_categories."
                        "product_public_category_view_form_merchant"
                    ).id,
                    "form",
                ),
            ],
            "domain": [("website_id", "=", website.id)]
            if website
            else [("website_id", "!=", False)],
            "context": {"default_website_id": website.id} if website else {},
            "target": "current",
        }
