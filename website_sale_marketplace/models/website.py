# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class Website(models.Model):
    _inherit = "website"

    is_marketplace = fields.Boolean(
        string="Marketplace",
        help="When enabled, this website's shop lists the published products of "
        "every company. It works by adding this website's company to each "
        "product's allowed companies, so the marketplace can see them while "
        "every other website keeps showing only its own company's products "
        "(product_multi_company isolation). Products still belong to their own "
        "merchant company; the marketplace company is only added as an extra "
        "visibility scope.",
    )

    @api.model
    def _marketplace_companies(self):
        """Companies that own at least one marketplace website."""
        return self.sudo().search([("is_marketplace", "=", True)]).company_id

    def _sync_marketplace_products(self):
        """Ensure every product is visible to this record's marketplace
        companies by adding them to the product ``company_ids`` m2m.

        A product visible to companies ``[merchant, marketplace]`` shows on both
        the merchant site and the marketplace, but never on a *different*
        merchant's site (that company is not in ``company_ids``), so isolation
        between merchants is preserved.
        """
        Product = self.env["product.template"].sudo()
        for company in self.filtered("is_marketplace").company_id:
            products = Product.search([("company_ids", "not in", company.ids)])
            if products:
                products.write(
                    {"company_ids": [fields.Command.link(company.id)]}
                )

    @api.model_create_multi
    def create(self, vals_list):
        websites = super().create(vals_list)
        websites._sync_marketplace_products()
        return websites

    def write(self, vals):
        res = super().write(vals)
        if {"is_marketplace", "company_id"} & set(vals):
            self._sync_marketplace_products()
        return res
