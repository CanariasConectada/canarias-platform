# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging
import re

from odoo import models
from odoo.fields import Command

_logger = logging.getLogger(__name__)

# The pickup method's user-facing name, the same on the carrier and on its
# service product. Spanish on purpose and not wrapped in _(): it is data the
# shopper reads at checkout, identical to the 148 carriers the migration
# brought, not an interface string.
PICKUP_CARRIER_NAME = "Retirar en la tienda (%s)"


class ResCompany(models.Model):
    _inherit = "res.company"

    def write(self, vals):
        """Sweep marketplace links when a merchant is archived.

        Archiving a merchant used to leave its products on the aggregated
        shop: the backfill had linked the portal company into their
        ``company_ids``, and the portal's record rule reads that link, not
        the owner's active flag. It took a manual SQL sweep every time a
        business left the platform (101racing on 2026-08-11 was the latest).

        Now the archival does it itself: after the write, any product whose
        every active real owner is gone loses its portal/zone marketplace
        links, so the record rule stops showing it — automatically, for every
        future retirement.
        """
        archiving = vals.get("active") is False
        res = super().write(vals)
        if archiving and self:
            self.env["product.template"]._wsm_sweep_orphaned_marketplace_links()
        return res

    # ------------------------------------------------------------------
    # In-store pickup carrier
    # ------------------------------------------------------------------
    def _ensure_shop_pickup_carrier(self, website=None):
        """Give this merchant shop its "pick up in store" delivery method.

        Without any carrier of its own, a shop's checkout stops at "No hay
        ningún método de envío disponible" and ``website_sale_collect``
        refuses the carrier recompute that writing ``company_ids`` on a
        product triggers. The migration gave 148 shops one; shops created
        afterwards got none.

        Idempotent: a company that already has any active carrier gets it
        back untouched. Marketplace companies (the portal and the zone
        shops) and companies without a website get nothing: they sell no
        goods of their own. Returns the carrier, or an empty recordset.

        :param website: the shop's website, when the caller already holds it
            (``res.company.website_id`` is a stored compute that lags behind
            a website created in the same transaction).
        """
        self.ensure_one()
        company = self.sudo()
        Carrier = self.env["delivery.carrier"].sudo()
        existing = Carrier.search([("company_id", "=", company.id)], limit=1)
        if existing:
            return existing
        Website = self.env["website"].sudo()
        if Website.search_count(
            [("company_id", "=", company.id), ("is_marketplace", "=", True)]
        ):
            return Carrier
        website = (website and website.sudo()) or Website.search(
            [("company_id", "=", company.id)], order="id", limit=1
        )
        if not website or website.is_marketplace:
            return Carrier
        warehouse = company._shop_pickup_warehouse()
        name = PICKUP_CARRIER_NAME % company.name
        # Not linked to the portal marketplace: the service product only
        # prices the method, it is never sold.
        product = (
            self.env["product.product"]
            .sudo()
            .with_context(wsm_skip_marketplace_link=True)
            .create(
                {
                    "name": name,
                    "type": "service",
                    "sale_ok": False,
                    "purchase_ok": False,
                    "list_price": 0.0,
                    "company_ids": [Command.set(company.ids)],
                }
            )
        )
        carrier = Carrier.create(
            {
                "name": name,
                "delivery_type": "in_store",
                "product_id": product.id,
                "company_id": company.id,
                "website_id": website.id,
                "fixed_price": 0.0,
                "invoice_policy": "estimated",
                "sequence": 10,
            }
        )
        # website_sale_collect's create links EVERY warehouse of the company
        # and publishes only if it found one; pin the shop's own warehouse.
        carrier.write(
            {"warehouse_ids": [Command.set(warehouse.ids)], "is_published": True}
        )
        _logger.info(
            "Pickup carrier %s (id %s) created for company %s (id %s) on "
            "website %s, warehouse %s (id %s).",
            name,
            carrier.id,
            company.name,
            company.id,
            website.id,
            warehouse.code,
            warehouse.id,
        )
        return carrier

    def _shop_pickup_warehouse(self):
        """The shop's warehouse, created when the company has none.

        Its address is the pickup address the checkout shows, so it must be
        the company's own partner. Companies created after the migration may
        have no warehouse at all (stock only creates one on company create
        while a test runs).
        """
        self.ensure_one()
        Warehouse = self.env["stock.warehouse"].sudo()
        warehouse = Warehouse.search(
            [("company_id", "=", self.id)], order="sequence, id", limit=1
        )
        if warehouse:
            if not warehouse.partner_id:
                warehouse.partner_id = self.partner_id
            return warehouse
        code = self._shop_pickup_warehouse_code()
        name = self.name
        # Warehouse names are unique per company, archived ones included.
        if Warehouse.with_context(active_test=False).search_count(
            [("company_id", "=", self.id), ("name", "=", name)]
        ):
            name = f"{name} ({code})"
        return Warehouse.create(
            {
                "name": name,
                "code": code,
                "company_id": self.id,
                "partner_id": self.partner_id.id,
            }
        )

    def _shop_pickup_warehouse_code(self):
        """A free code of at most 5 chars: the name's letters, else ``W<id>``."""
        self.ensure_one()
        taken = set(
            self.env["stock.warehouse"]
            .sudo()
            .with_context(active_test=False)
            .search([("company_id", "=", self.id)])
            .mapped("code")
        )
        letters = re.sub(r"[^A-Za-z0-9]", "", self.name or "").upper()[:5]
        for code in (letters, f"W{self.id}"[:5], str(self.id)[-5:]):
            if code and code not in taken:
                return code
        return f"W{len(taken)}"[:5]
