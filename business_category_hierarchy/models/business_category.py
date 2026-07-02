# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class BusinessCategory(models.Model):
    _name = "business.category"
    _description = "Business Category"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "complete_name"

    name = fields.Char(
        required=True,
        translate=True,
    )
    parent_id = fields.Many2one(
        comodel_name="business.category",
        string="Parent Category",
        index=True,
        ondelete="cascade",
        help="Leave empty to create a root category (level 1).",
    )
    parent_path = fields.Char(index=True)
    child_ids = fields.One2many(
        comodel_name="business.category",
        inverse_name="parent_id",
        string="Subcategories",
    )
    complete_name = fields.Char(
        compute="_compute_complete_name",
        recursive=True,
        store=True,
        index=True,
    )
    active = fields.Boolean(
        default=True,
        help="Archived categories are no longer selectable on companies.",
    )
    hierarchy_level = fields.Integer(
        string="Level",
        compute="_compute_hierarchy_level",
        recursive=True,
        store=True,
        help="Depth in the hierarchy: 1 for root categories, "
        "2 for subcategories, and so on.",
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="business_category_res_company_rel",
        column1="business_category_id",
        column2="res_company_id",
        string="Companies",
        readonly=True,
    )
    company_count = fields.Integer(
        string="# Companies",
        compute="_compute_company_count",
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = (
                    f"{category.parent_id.complete_name} / {category.name}"
                )
            else:
                category.complete_name = category.name

    @api.depends("parent_id.hierarchy_level")
    def _compute_hierarchy_level(self):
        for category in self:
            category.hierarchy_level = category.parent_id.hierarchy_level + 1

    @api.depends("company_ids")
    def _compute_company_count(self):
        for category in self:
            category.company_count = len(category.company_ids)

    @api.depends("complete_name")
    def _compute_display_name(self):
        for category in self:
            category.display_name = category.complete_name or category.name

    @api.constrains("parent_id")
    def _check_category_recursion(self):
        if self._has_cycle():
            raise ValidationError(self.env._("You cannot create recursive categories."))

    @api.model
    def name_create(self, name):
        # The default name_create would write the name into _rec_name, which
        # here is the computed (read-only) complete_name.
        record = self.create({"name": name})
        return record.id, record.display_name
