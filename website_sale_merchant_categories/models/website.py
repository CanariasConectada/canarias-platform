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
        return self.env["website.category.tile"]._action_for_website(self)

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
