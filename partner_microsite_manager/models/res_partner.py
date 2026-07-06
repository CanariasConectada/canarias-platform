# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    # Convenience bridge kept from the legacy module: the microsite content
    # now lives on res.company, but users often land on the contact form
    # first, so the partner form shows a smart button to jump to it.
    microsite_company_id = fields.Many2one(
        "res.company",
        compute="_compute_microsite_company_id",
        string="Microsite Company",
        help="Company of this contact that owns a website (microsite).",
    )
    has_microsite = fields.Boolean(compute="_compute_microsite_company_id")

    # No @api.depends: the field is not stored and there is no relational
    # path from res.partner to res.company in Odoo 19 base (the old
    # ref_company_ids one2many is gone), so it is simply recomputed on read.
    def _compute_microsite_company_id(self):
        companies = (
            self.env["res.company"]
            .sudo()
            .search([("partner_id", "in", self.ids), ("website_id", "!=", False)])
        )
        mapping = {company.partner_id.id: company.id for company in companies}
        for partner in self:
            partner.microsite_company_id = mapping.get(partner.id, False)
            partner.has_microsite = bool(partner.microsite_company_id)

    def action_open_microsite_company(self):
        """Open the company form (Microsite tab) of this contact."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Microsite"),
            "res_model": "res.company",
            "res_id": self.microsite_company_id.id,
            "view_mode": "form",
            "target": "current",
        }
