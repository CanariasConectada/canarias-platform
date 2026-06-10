# Copyright 2026 Tu Empresa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models


class ResCompany(models.Model):
    """Extensión de res.company para añadir categorías de comercio."""

    _inherit = "res.company"

    business_category_ids = fields.Many2many(
        comodel_name="business.category",
        relation="business_category_res_company_rel",
        column1="res_company_id",
        column2="business_category_id",
        string="Categorías de Comercio",
        help="Categorías de comercio para segmentar esta empresa. "
             "Puede seleccionar múltiples categorías.",
    )

    # Campo legacy computado para backward compatibility
    business_category_id = fields.Many2one(
        comodel_name="business.category",
        string="Categoría de Comercio",
        compute="_compute_business_category_id",
        inverse="_inverse_business_category_id",
        store=False,
        help="Categoría principal de comercio (compatibilidad legacy).",
    )

    @api.depends("business_category_ids")
    def _compute_business_category_id(self):
        """Devuelve la primera categoría del Many2many para compatibilidad."""
        for company in self:
            company.business_category_id = company.business_category_ids[:1].id or False

    def _inverse_business_category_id(self):
        """Al escribir business_category_id, sincroniza con business_category_ids."""
        for company in self:
            if company.business_category_id:
                company.business_category_ids = [(4, company.business_category_id.id, 0)]
            else:
                company.business_category_ids = [(5, 0, 0)]
