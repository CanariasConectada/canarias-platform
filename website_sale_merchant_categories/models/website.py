# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, models


class Website(models.Model):
    _inherit = "website"

    def _wsc_category_tile(self, node, covered_ids):
        """This shop's own picture for the node first, the shared cover after.

        A merchant's override is looked up for every member of the merged
        node, in the tile's own order, so the picture never depends on which
        member happens to be the URL's representative. A row without an
        image curates nothing and is skipped, exactly like a category
        without a cover: today's behaviour stays for every node no merchant
        touched. ``sudo`` because the shop is a public page and the visitor
        has no business reading tile rows -- what they get is a URL.
        """
        self.ensure_one()
        override = (
            self.env["website.category.tile"]
            .sudo()
            .search(
                [
                    ("website_id", "=", self.id),
                    ("category_id", "in", node["categories"].ids),
                    ("image", "!=", False),
                ],
                limit=1,
            )
        )
        if not override:
            return super()._wsc_category_tile(node, covered_ids)
        return {
            "id": node["id"],
            "name": override.name or node["name"],
            "category": node["categories"].sorted("id")[0],
            "image_url": self.image_url(override, "image", "400x400"),
        }

    def _wsmc_shop_category_choices(self):
        """The categories a tile of this shop may be made for.

        What the shop's products carry (the same set the sidebar and the tile
        row are built from) plus the categories that belong to this site
        alone, which may not have a product yet. Read as the caller, like
        ``_wsc_shop_categories`` itself.
        """
        self.ensure_one()
        own = self.env["product.public.category"].search([("website_id", "=", self.id)])
        return self._wsc_shop_categories() | own

    def action_microsite_categories(self):
        """The category tiles of this site's shop (button on "My shops")."""
        self._pmm_assert_own_site()
        self._wsmc_sync_category_rows()
        return self.env["website.category.tile"]._action_for_website(self)

    def _wsmc_row_categories(self):
        """Every category the "Shop categories" screen lists for this shop.

        The shop's OWN categories, with or without a product, and the SHARED
        categories its sellable products carry, published or not: a merchant
        preparing a product must be able to prepare its tile too. Read with
        sudo because it decides rows, never what a visitor sees; the caller
        has already been checked against the site.
        """
        self.ensure_one()
        Category = self.env["product.public.category"].sudo()
        Product = self.env["product.template"].sudo()
        company_field = (
            "company_ids" if "company_ids" in Product._fields else "company_id"
        )
        products = Product.search(
            [(company_field, "in", self.company_id.ids), ("sale_ok", "=", True)]
        )
        shared = products.public_categ_ids.filtered(lambda c: not c.website_id)
        return Category.search([("website_id", "=", self.id)]) | shared

    def _wsmc_ensure_category_rows(self, categories):
        """Create the missing tile rows of ``categories`` on this site.

        ``sudo``: a row is bookkeeping of a category the caller was already
        allowed to own or to sell under. An empty row curates nothing on the
        shop (see ``_wsc_category_tile``).
        """
        self.ensure_one()
        Tile = self.env["website.category.tile"].sudo()
        existing = Tile.search(
            [("website_id", "=", self.id), ("category_id", "in", categories.ids)]
        ).category_id
        missing = categories - existing
        if missing:
            Tile.create([{"website_id": self.id, "category_id": c.id} for c in missing])

    def _wsmc_sync_category_rows(self):
        """Make the screen list every category of the shop, one row each.

        Asked for on 2026-09-16: a merchant created two own categories and
        the screen stayed empty, because rows only existed when added by
        hand. Missing rows are created; rows of categories the shop no
        longer uses are removed only when they carry neither an image nor a
        label, so nothing the merchant curated is ever lost.
        """
        for website in self:
            website._pmm_assert_own_site()
        Tile = self.env["website.category.tile"].sudo()
        for website in self:
            wanted = website._wsmc_row_categories()
            website._wsmc_ensure_category_rows(wanted)
            Tile.search(
                [
                    ("website_id", "=", website.id),
                    ("category_id", "not in", wanted.ids),
                    ("image", "=", False),
                    ("name", "in", [False, ""]),
                ]
            ).unlink()

    def _wsmc_merchant_websites(self):
        """The sites a merchant may pin a category to: their real shops.

        ``_get_editable_microsite_companies`` is the single authority on
        which companies the caller runs a shop for -- it already leaves out
        the platform's own company and the bookkeeping zone companies
        ``zone_company_ownership`` puts in every merchant's allowed list.
        A zone's marketplace is nobody's shop, so it is refused here too even
        if it slipped through.
        """
        companies = self.env["res.company"]._get_editable_microsite_companies()
        return self.sudo().search(
            [("company_id", "in", companies.ids), ("is_marketplace", "=", False)]
        )

    def _wsmc_no_shop_message(self):
        return _(
            "Your account is not linked to a shop with its own site, so it "
            "cannot own a category."
        )
