# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import Command, api, models
from odoo.http import request

# The customer fields website_sale fills in with the shopper's own partner.
WEBSITE_CUSTOMER_FIELDS = frozenset(
    {"partner_id", "partner_invoice_id", "partner_shipping_id"}
)


class SaleOrder(models.Model):
    _inherit = "sale.order"

    def _wsm_is_website_customer_flow(self):
        """True for a shop order handled in a shopper's own request.

        Only a request from a non-internal user (portal or public) on an order
        that belongs to a website qualifies: every backend path, and an
        internal user shopping on a website, keeps core's checks untouched.
        """
        self.ensure_one()
        return bool(request and self.website_id and not request.env.user._is_internal())

    def _check_company(self, fnames=None):
        """Do not reject a shop order because of where its CUSTOMER lives.

        A logged-in shopper's partner is restricted (partner_multi_company) to
        the shopper's own company, a commercial zone for most of them. On a
        merchant website of that zone, ``website/models/ir_http.py`` switches
        the request to the user's company and ``website_sale._create_cart``
        builds an order of the WEBSITE company for that partner, so core's
        ``_check_company`` raised "company inconsistencies" on ``partner_id``,
        ``partner_invoice_id`` and ``partner_shipping_id`` and no logged-in
        zone customer could even open a cart. Anonymous carts never hit it:
        the public partner is not restricted.

        The shopper is the customer of the order, not company data: those three
        fields are left out of the check for website orders in the shopper's
        own request. Every other field (pricelist, fiscal position, team,
        warehouse...) is still checked.
        """
        website_orders = self.filtered(lambda o: o._wsm_is_website_customer_flow())
        backend_orders = self - website_orders
        if backend_orders:
            super(SaleOrder, backend_orders)._check_company(fnames=fnames)
        if not website_orders:
            return
        # Core expands to every field when the company itself is checked;
        # expand here first so the customer fields can be removed.
        if fnames is None or {"company_id", "company_ids"} & set(fnames):
            fnames = list(self._fields)
        fnames = [
            name
            for name in fnames
            if name not in WEBSITE_CUSTOMER_FIELDS
            and name not in ("company_id", "company_ids")
        ]
        return super(SaleOrder, website_orders)._check_company(fnames=fnames)

    def _action_confirm(self):
        """Make the shop's customer usable by the shop once they buy.

        The exemption in ``_check_company`` only covers the cart. Confirming
        creates the documents the merchant works with (delivery orders, then
        invoices), and those check the customer's company too: a zone
        customer's partner, restricted to the zone, made ``stock.picking``
        refuse the confirmation. The merchant must also be able to open its
        own customer in the backend.

        So the order's company is linked to the customer's commercial partner
        (``company_ids`` is a commercial field, synced to its addresses) when
        that partner is restricted to other companies. Only at confirmation:
        a shop learns who its buyers are, never who merely opened a cart.
        Unrestricted partners (empty ``company_ids``) are left alone, as
        linking a company would restrict them instead.

        Not gated on the request: payment post-processing may confirm the
        order from a cron or a provider webhook.
        """
        for order in self.filtered("website_id"):
            partners = (
                (
                    order.partner_id
                    | order.partner_invoice_id
                    | order.partner_shipping_id
                )
                .sudo()
                .commercial_partner_id
            )
            restricted = partners.filtered(
                lambda p, company=order.company_id: p.company_ids
                and company not in p.company_ids
            )
            if restricted:
                restricted.write({"company_ids": [Command.link(order.company_id.id)]})
        return super()._action_confirm()

    @api.constrains("company_id", "order_line")
    def _check_order_line_company_id(self):
        """Resolve each product's company against the ORDER's company.

        ``base_multi_company`` computes ``product.company_id`` from the
        request's allowed companies: a product linked to [shop, zone, portal]
        resolves to the ZONE when a zone customer's request runs with the zone
        as its company, and core then refuses the shop's own product ("Your
        quotation contains products from company ..."). Core also measures
        the order's company through ``_accessible_branches``, which is empty
        when the order's company is not among the allowed ones. ``_cart_add``
        already works ``with_company(order.company_id)``; this constraint runs
        on whatever env the write came from, so it is given the same company.

        A product that is NOT linked to the order's company still resolves to
        another company and is still refused.
        """
        website_orders = self.filtered(lambda o: o._wsm_is_website_customer_flow())
        for order in website_orders:
            order = order.with_company(order.company_id)
            # product.product.company_id is related to the template's
            # computed field: drop cached values computed for another company.
            order.order_line.product_id.invalidate_recordset(["company_id"])
            super(SaleOrder, order)._check_order_line_company_id()
        return super(SaleOrder, self - website_orders)._check_order_line_company_id()
