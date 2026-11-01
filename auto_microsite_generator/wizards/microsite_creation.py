# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from ..models.res_company import _normalize_subdomain


class MicrositeCreationWizard(models.TransientModel):
    """Ask for the subdomain, then build the microsite.

    The point of this screen is the order of events. DNS here is manual -- no
    registrar API, a wildcard certificate renewed by hand -- so the hostname
    has to be decided by a person and pointed at the server before a site
    starts answering on it. Creating the website first and discovering the
    address afterwards is how a merchant ends up with a shop nobody can
    reach.
    """

    _name = "microsite.creation.wizard"
    _description = "Create Microsite"

    company_id = fields.Many2one(
        "res.company",
        string="Shop",
        required=True,
        readonly=True,
    )
    subdomain = fields.Char(
        required=True,
        help=(
            "The DNS label only: type 'neveri' and the microsite answers at "
            "https://neveri.canariasconectada.es."
        ),
    )
    domain_suffix = fields.Char(readonly=True)
    address = fields.Char(
        string="Microsite Address",
        compute="_compute_address",
        help="The exact address the microsite will answer at.",
    )
    dns_record = fields.Char(
        string="DNS Record",
        compute="_compute_address",
        help="The record to create at the registrar before publishing.",
    )

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        company = self.env["res.company"].browse(self.env.context.get("active_id"))
        if company.exists():
            values.setdefault("company_id", company.id)
            # A suggestion, never a decision: prefilled from the trade name so
            # the common case is one keystroke, and fully editable because
            # "neveriobradorartesanalsociedad" is what happens when nobody is
            # asked.
            values.setdefault(
                "subdomain",
                company.microsite_subdomain or _normalize_subdomain(company.name),
            )
        values.setdefault(
            "domain_suffix", self.env["res.company"]._microsite_domain_suffix()
        )
        return values

    @api.depends("subdomain", "domain_suffix")
    def _compute_address(self):
        for wizard in self:
            if wizard.subdomain and wizard.domain_suffix:
                wizard.address = f"https://{wizard.subdomain}{wizard.domain_suffix}"
                wizard.dns_record = (
                    f"{wizard.subdomain}{wizard.domain_suffix} -> this server"
                )
            else:
                wizard.address = ""
                wizard.dns_record = ""

    def action_create_microsite(self):
        """Name the subdomain, provision the site, and open it.

        The subdomain is written first and on its own: its constraint is what
        rejects a malformed or already-taken label, and it has to reject it
        *before* a website exists, not after.
        """
        self.ensure_one()
        company = self.company_id
        if company.website_id:
            raise UserError(
                _(
                    "%(company)s already has a microsite at %(address)s.",
                    company=company.display_name,
                    address=company.website_id.domain or company.website_id.name,
                )
            )
        company.microsite_subdomain = (self.subdomain or "").strip().lower()
        company._auto_generate_microsite()
        if not company.website_id:
            raise UserError(
                _(
                    "The microsite for %(company)s could not be created. Check "
                    "the server log for the reason.",
                    company=company.display_name,
                )
            )
        return {
            "type": "ir.actions.act_window",
            "res_model": "website",
            "res_id": company.website_id.id,
            "view_mode": "form",
            "target": "current",
        }
