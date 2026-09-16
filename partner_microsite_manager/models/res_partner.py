# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import AccessError


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
        """Open the microsite content of this contact's shop.

        Whoever may write companies (administrators) gets the company form,
        whose Microsite page mirrors the content editor. Everybody else --
        the merchants, who read companies but write none -- used to land on
        that same form read-only (client report 2026-09-16). They get the
        content editor instead, through the website's own action, so the
        ownership guard applies: another shop's contact is refused with
        ``AccessError``, never answered with that shop's editor.
        """
        self.ensure_one()
        company = self.sudo().microsite_company_id
        if not self.env["res.company"].has_access("write"):
            if not company:
                raise AccessError(_("This contact has no microsite."))
            return company.website_id.with_env(self.env).action_microsite_content()
        return {
            "type": "ir.actions.act_window",
            "name": _("Microsite"),
            "res_model": "res.company",
            "res_id": company.id,
            "view_mode": "form",
            "views": [(False, "form")],
            "target": "current",
        }
