# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class MicrositeCompanyPicker(models.TransientModel):
    """The extra step an owner of SEVERAL shops sees before the editor.

    Shown only when ``res.company._get_own_microsite_companies()`` has more
    than one record (see ``microsite.content.editor.action_open_page_content``);
    an owner of a single shop never sees this screen at all.

    This wizard does not decide who may edit what: it hands its own choice
    of company id to ``microsite.content.editor._resolve_target_company()``,
    the platform's single authority on the question, and shapes the action
    that follows. Picking a company here is a REQUEST like any other; it is
    checked exactly as a forged one would be.
    """

    _name = "microsite.company.picker"
    _description = "Choose which of your shops to edit"

    company_ids = fields.Many2many(
        comodel_name="res.company",
        string="Your shops",
        compute="_compute_company_ids",
        help="Every real shop of yours that has its own site.",
    )
    selected_company_id = fields.Many2one(
        comodel_name="res.company",
        string="Shop to edit",
        domain="[('id', 'in', company_ids)]",
        help="Pick one of your own shops. Its address is shown below so two "
        "similarly named shops are not confused.",
    )
    selected_company_website_url = fields.Char(
        string="Address",
        related="selected_company_id.website_id.domain",
        readonly=True,
    )

    def _compute_company_ids(self):
        companies = self.env["res.company"]._get_own_microsite_companies()
        for picker in self:
            picker.company_ids = companies

    def action_open_editor(self):
        """Open the content editor for the chosen shop.

        Validation is NOT re-implemented here: it is delegated wholesale to
        ``microsite.content.editor._resolve_target_company()``. This method
        only hands over the picker's choice and shapes the resulting action;
        a stale or tampered id is refused there, exactly as it would be
        anywhere else on this screen.
        """
        self.ensure_one()
        if not self.selected_company_id:
            raise UserError(_("Please choose a shop first."))
        company = self.env["microsite.content.editor"]._resolve_target_company(
            self.selected_company_id.id
        )
        return {
            "type": "ir.actions.act_window",
            "name": _("Page content"),
            "res_model": "microsite.content.editor",
            "view_mode": "form",
            "target": "new",
            "context": {"microsite_company_id": company.id},
        }
