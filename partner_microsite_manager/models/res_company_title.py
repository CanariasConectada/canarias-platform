# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The cover-title contract of the microsite: the resolved title field, its
fallback hook and the help text shared by every place a merchant can type the
cover title. Split out of ``res_company.py`` (1.7k lines) so the contract is
readable on its own."""

from odoo import api, fields, models

# One help text for the two places the merchant can type the cover title
# (the company form and the page content editor), so the tooltip never
# says two different things about the same value. It describes the chain
# as deployed, i.e. with website_directory_partner_microsite installed; see
# _compute_microsite_title for what this module does on its own.
MICROSITE_COVER_TITLE_HELP = (
    "Title shown on the microsite cover. If left empty, the trade name is used."
)


class ResCompany(models.Model):
    _inherit = "res.company"

    microsite_title = fields.Char(
        string="Microsite cover title (resolved)",
        compute="_compute_microsite_title",
        help="What the microsite cover actually prints: the cover title typed "
        "by the merchant, else the fallback of the installed modules.",
    )

    def _get_microsite_title_fallback(self):
        """What the cover shows when no cover title was typed.

        Hook: this module knows nothing but the legal name. Bridge modules
        that know where the trade name lives override it and call super()
        as their own last resort.
        """
        self.ensure_one()
        return self.name

    @api.depends("microsite_name", "name")
    def _compute_microsite_title(self):
        """The single place that decides what the cover shows.

        The hero H1, the hidden lead name of the contact form and the footer
        heading all read this field instead of repeating the fallback in
        three templates. The full chain, as deployed on the platform with
        ``website_directory_partner_microsite`` installed, is: cover title
        typed by the merchant, then trade name (``res.company.comercial``,
        from ``res_company_zone``), then legal name -- which is what the
        field's help text promises the merchant. This module standing alone
        has no trade name and falls back straight to the legal name; the
        bridge slots the trade name in through
        :meth:`_get_microsite_title_fallback`.
        """
        for company in self:
            company.microsite_title = (
                company.microsite_name or ""
            ).strip() or company._get_microsite_title_fallback()
