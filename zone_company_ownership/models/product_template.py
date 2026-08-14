# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, models

from .res_company import SKIP_CONTEXT


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "zone.company.ownership.mixin"]

    def _zone_sync_candidates(self):
        """Delivery methods are not catalogue, so they get no zone.

        ``multi.company.abstract`` computes ``company_id`` out of
        ``company_ids``, and a delivery carrier takes its company from the
        product behind it. Adding a zone company to the "Recogida en tienda"
        product therefore moves the carrier to a different company than its
        warehouse, and ``website_sale_collect`` rejects the write -- correctly:
        a delivery method belongs to the shop that ships, not to a
        neighbourhood. Nobody browses these in a zone shop either, so there is
        nothing to gain by including them.
        """
        candidates = super()._zone_sync_candidates()
        if "delivery.carrier" not in self.env:
            return candidates
        carriers = self.env["delivery.carrier"].sudo().with_context(active_test=False)
        excluded = carriers.search([]).product_id.product_tmpl_id
        return candidates - excluded

    @api.model_create_multi
    def create(self, vals_list):
        products = super().create(vals_list)
        if not self.env.context.get(SKIP_CONTEXT):
            products._apply_zone_companies()
        return products

    def write(self, vals):
        res = super().write(vals)
        # Only an ownership edit can change which zone applies. Reacting to
        # every write would re-derive the zone companies of the whole
        # catalogue every time somebody fixed a typo in a description.
        if ("company_ids" in vals or "company_id" in vals) and not self.env.context.get(
            SKIP_CONTEXT
        ):
            self._apply_zone_companies()
        return res
