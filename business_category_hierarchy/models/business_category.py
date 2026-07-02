# Copyright 2026 Tu Empresa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class BusinessCategory(models.Model):
    """Modelo para gestionar categorías jerárquicas de comercio.
    
    Soporta 3 niveles de jerarquía:
    - Nivel 1: Categorías Principales (sin padre)
    - Nivel 2: Subcategorías (hijas de principales)
    - Nivel 3: Especialidades (hijas de subcategorías)
    """

    _name = "business.category"
    _description = "Categoría de Comercio"
    _parent_name = "parent_id"
    _parent_store = True
    _rec_name = "complete_name"
    _order = "complete_name"

    name = fields.Char(
        string="Nombre",
        required=True,
        translate=True,
    )
    parent_id = fields.Many2one(
        comodel_name="business.category",
        string="Categoría Padre",
        index=True,
        ondelete="cascade",
        help="Seleccione la categoría padre. Deje vacío para crear una categoría principal (Nivel 1).",
    )
    parent_path = fields.Char(
        index=True,
    )
    child_ids = fields.One2many(
        comodel_name="business.category",
        inverse_name="parent_id",
        string="Subcategorías",
    )
    complete_name = fields.Char(
        string="Nombre Completo",
        compute="_compute_complete_name",
        recursive=True,
        store=True,
        index=True,
    )
    active = fields.Boolean(
        default=True,
        help="Si está desactivado, la categoría no estará disponible para selección.",
    )
    
    # Campos computados para facilitar el trabajo
    hierarchy_level = fields.Integer(
        string="Nivel",
        compute="_compute_hierarchy_level",
        store=True,
        recursive=True,
        help="Nivel en la jerarquía: 1=Principal, 2=Subcategoría, 3=Especialidad",
    )
    company_count = fields.Integer(
        string="Nº Empresas",
        compute="_compute_company_count",
        store=False,
    )
    company_ids = fields.Many2many(
        comodel_name="res.company",
        relation="business_category_res_company_rel",
        column1="business_category_id",
        column2="res_company_id",
        string="Empresas",
        readonly=True,
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self) -> None:
        """Calcula el nombre completo incluyendo la jerarquía."""
        for category in self:
            if category.parent_id:
                category.complete_name = (
                    f"{category.parent_id.complete_name} / {category.name}"
                )
            else:
                category.complete_name = category.name
    
    @api.depends("parent_id", "parent_id.hierarchy_level")
    def _compute_hierarchy_level(self) -> None:
        """Calcula el nivel jerárquico (1, 2 o 3)."""
        for category in self:
            if not category.parent_id:
                category.hierarchy_level = 1
            elif not category.parent_id.parent_id:
                category.hierarchy_level = 2
            else:
                category.hierarchy_level = 3
    
    def _compute_company_count(self) -> None:
        """Calcula el número de empresas con esta categoría."""
        for category in self:
            category.company_count = len(category.company_ids)

    def _compute_display_name(self) -> None:
        """Sobreescribe para usar complete_name como display_name."""
        for category in self:
            category.display_name = category.complete_name or category.name

    @api.constrains("parent_id")
    def _check_category_recursion(self) -> None:
        """Verifica que no existan ciclos en la jerarquía."""
        if self._has_cycle():
            raise ValidationError(
                "Error: No puedes crear categorías recursivas "
                "(una categoría no puede ser hija de sí misma)."
            )

    @api.model
    def name_create(self, name: str) -> tuple[int, str]:
        """Permite crear categorías rápidamente desde campos Many2one.

        Override necesario porque _rec_name es "complete_name" (computado,
        no se puede escribir directamente); el name_create del core
        intentaría crear el registro con {"complete_name": name}.
        """
        record = self.create({"name": name})
        return record.id, record.display_name

    def unlink(self):
        """
        Override unlink to also remove ir.model.data references.
        This prevents deleted categories from being recreated on module update.
        """
        # Remove ir.model.data references for these records
        if self.ids:
            self.env['ir.model.data'].sudo().search([
                ('model', '=', self._name),
                ('res_id', 'in', self.ids)
            ]).unlink()
        return super().unlink()
