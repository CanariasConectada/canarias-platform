# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models

from .res_company import SKIP_CONTEXT


class ProductTemplate(models.Model):
    _name = "product.template"
    _inherit = ["product.template", "zone.company.ownership.mixin"]

    # See the twin declaration on ``res.partner`` for why this cannot live
    # on the mixin: the default relation table would collide with the one
    # ``company_ids`` already occupies.
    zone_company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="product_template_zone_company_rel",
        column1="product_tmpl_id",
        column2="company_id",
        string="Commercial Zone",
        compute="_compute_zone_company_ids",
        store=True,
        help="The zone companies among this product's owners. Derived from "
        "the owning shop's commercial zone; group or filter by it to see a "
        "neighbourhood's catalogue together.",
    )

    @api.depends("company_ids", "company_ids.zone_company_key")
    def _compute_zone_company_ids(self):
        return super()._compute_zone_company_ids()

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
