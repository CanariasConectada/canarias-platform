# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import AccessError

from .res_company import _live_values_change, clear_templates_cache_on_commit

# Partner fields the live blocks of a legacy homepage render.
LIVE_PARTNER_FIELDS = frozenset(
    {"phone", "email", "street", "street2", "zip", "city", "website"}
)
# The page kind each partner field feeds (the map follows the address: it
# is built from it when the shop has no map link of its own).
PARTNER_FIELD_KINDS = {
    "email": ("email",),
    "street": ("address", "map"),
    "street2": ("address", "map"),
    "zip": ("address", "map"),
    "city": ("address", "map"),
    "website": ("website",),
}


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

    def write(self, vals):
        """Keep the shop's legacy homepage in step with its contact data.

        - The page cache is emptied (at commit) when a rendered value really
          changes: public pages are cached an hour per page, and the company
          form and the directory write the partner directly.
        - The kinds a person just changed go live on the page, even where
          the migration kept the importer's text because it differed: from
          now on the human edit wins. A kind left empty is not forced.
        """
        live_changed = _live_values_change(self, LIVE_PARTNER_FIELDS, vals)
        changed_fields = [
            name
            for name in PARTNER_FIELD_KINDS
            if name in vals and _live_values_change(self, frozenset({name}), vals)
        ]
        result = super().write(vals)
        if live_changed:
            companies = (
                self.env["res.company"]
                .sudo()
                .search([("partner_id", "in", self.ids), ("website_id", "!=", False)])
            )
            if companies:
                clear_templates_cache_on_commit(self.env)
                for company in companies:
                    kinds = {
                        kind
                        for name in changed_fields
                        for kind in PARTNER_FIELD_KINDS[name]
                        if company._microsite_live_has(kind)
                    }
                    company._relink_after_human_edit(kinds)
        return result

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
