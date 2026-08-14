# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import api, models
from odoo.fields import Domain

# How many products to auto-recommend when a shop has not curated its own
# alternatives. Overridable per-database through the config parameter below so
# an admin can tune the carousel length without a code change.
DEFAULT_RECOMMENDED_LIMIT = 8
RECOMMENDED_LIMIT_PARAM = "shop_frontend_tweaks.recommended_limit"


class ProductTemplate(models.Model):
    _inherit = "product.template"

    def _get_website_alternative_product(self):
        """Hybrid recommendations for the product-page carousel.

        Odoo's carousel only ever shows the alternatives a shop curated by hand
        (``alternative_product_ids``). On a directory of hundreds of small
        shops almost none of them fill that field, so the section the theme
        promises -- "other products from this shop" -- renders empty nearly
        everywhere.

        Hybrid behaviour:

        * If the shop curated alternatives, those win untouched (manual
          override). A merchant who took the trouble to pick alternatives keeps
          full control.
        * Otherwise, fall back to other published products from the SAME shop.

        The fallback never mixes products across shops: it is anchored on the
        product's OWNING MERCHANT, so one merchant's catalogue can never
        surface under another's product. That explicit scope IS the isolation
        guarantee here, not a redundant nicety: ``product_multi_company`` ships
        no ``ir.rule`` on the ``company_ids`` m2m (only core's rule on the
        single ``company_id`` field), so nothing at the ORM layer backstops a
        loose domain.

        Why the anchor is the owning merchant and not the browsed website's
        company: ``website_sale_marketplace`` links the PORTAL marketplace
        company into every merchant product's ``company_ids`` (that is what
        puts them on the marketplace). On the portal, anchoring on the site's
        company would therefore match EVERY shop's catalogue -- under a heading
        that promises "other products from this shop". Subtracting the
        marketplace companies leaves exactly the owning merchant (verified:
        every companied product on this platform has exactly one), and the
        same anchor is correct on the portal and on the merchant's own
        microsite alike. Website visibility on top of it is already enforced
        by ``sale_product_domain()``.
        """
        curated = super()._get_website_alternative_product()
        # Only single, un-curated templates get the auto fallback. Multi-record
        # calls keep the exact base behaviour (the sole core caller always
        # browses a single template, so this branch is the real path).
        if curated or len(self) != 1:
            return curated
        return self._cc_auto_recommended_products()

    def _cc_auto_recommended_products(self):
        """Other published products from the same shop, excluding this one."""
        self.ensure_one()
        # Start from the same domain the core alternative/accessory helpers use:
        # it enforces website scoping, sale_ok and (for public visitors) the
        # published flag. base_multi_company rewrites its company_id leaf onto
        # the company_ids m2m, so it already isolates by shop at the SQL level.
        domain = Domain(self.env["website"].sale_product_domain())
        if not self.env.user._is_internal():
            domain &= Domain("is_published", "=", True)
        domain &= Domain("id", "!=", self.id)
        # Same-shop isolation, anchored on the OWNING MERCHANT (this product's
        # companies minus the marketplace companies -- see the class docstring
        # for why the browsed website's company is the wrong anchor). A
        # shared/global product (no company) recommends other shared products;
        # a product living only in marketplace scopes has no shop to speak of,
        # so it gets no auto recommendations rather than someone else's.
        merchants = self._cc_merchant_companies()
        if merchants:
            domain &= Domain("company_ids", "in", merchants.ids)
        elif self.company_ids:
            return self.browse()
        else:
            domain &= Domain("company_ids", "=", False)
        return self.env["product.template"].search(
            domain, limit=self._cc_recommended_limit()
        )

    def _cc_merchant_companies(self):
        """The real shop(s) owning this product: companies that are not a
        marketplace. Soft-checks the ``is_marketplace`` flag so this module
        keeps working (anchor = all companies) without the marketplace addon.
        """
        self.ensure_one()
        website_model = self.env["website"]
        if "is_marketplace" not in website_model._fields:
            return self.company_ids
        marketplace_companies = (
            website_model.sudo().search([("is_marketplace", "=", True)]).company_id
        )
        return self.company_ids - marketplace_companies

    @api.model
    def _cc_recommended_limit(self):
        """Carousel length, read from an overridable config parameter."""
        value = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(RECOMMENDED_LIMIT_PARAM, default=DEFAULT_RECOMMENDED_LIMIT)
        )
        try:
            limit = int(value)
        except (TypeError, ValueError):
            limit = DEFAULT_RECOMMENDED_LIMIT
        return limit if limit > 0 else DEFAULT_RECOMMENDED_LIMIT
