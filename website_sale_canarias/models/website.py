# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import models
from odoo.fields import Domain


class Website(models.Model):
    _inherit = "website"

    def _wsc_zone_label(self):
        """Human label of this website's marketplace zone, or False.

        The selection lives on ``marketplace_zone`` (website_sale_marketplace)
        and is only populated when res_company_zone is installed; an empty
        selection or no zone both answer False, so the hero template can fall
        back to the portal wording without special cases.
        """
        self.ensure_one()
        if not self.marketplace_zone:
            return False
        selection = self._fields["marketplace_zone"]._description_selection(self.env)
        return dict(selection).get(self.marketplace_zone) or False

    def _wsc_shop_domain(self):
        """What this website's shop really lists, published-only.

        ``sale_product_domain()`` is the platform's single source of truth for
        the shop's product set — website_sale_marketplace already reshapes it
        for the portal and the zone shops. The explicit ``is_published`` leaf
        is NOT redundant: the callers search as sudo (a visitor cannot read
        other merchants' companies), and sudo bypasses the record rule that
        would otherwise hide unpublished products.
        """
        self.ensure_one()
        return Domain(self.sale_product_domain()) & Domain("is_published", "=", True)

    def _wsc_shop_categories(self):
        """Public categories of the products this website's shop lists.

        Computed from the shop domain rather than from all categories so a
        zone shop only offers the categories of its own neighbourhood — the
        same behaviour the legacy shop implemented per website type by hand.

        Read as the CURRENT user, not sudo: the shop is a public page and the
        ``website_published`` record rule is what keeps one merchant's
        microsite from listing another's categories. sudo would drop that
        second line of defence and lean the whole isolation on the domain
        being exactly right — which is precisely the mistake to avoid on the
        page a visitor reaches.
        """
        self.ensure_one()
        products = self.env["product.template"].search(self._wsc_shop_domain())
        categories = products.public_categ_ids
        return categories.sorted(lambda category: (category.name or "").lower())
