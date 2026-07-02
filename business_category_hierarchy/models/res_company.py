# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    business_category_ids = fields.Many2many(
        comodel_name="business.category",
        relation="business_category_res_company_rel",
        column1="res_company_id",
        column2="business_category_id",
        string="Business Categories",
        help="Business categories used to segment this company, "
        "e.g. in the public directory.",
    )
