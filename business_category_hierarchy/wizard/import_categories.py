# Copyright 2026 Tu Empresa
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import api, fields, models
from odoo.exceptions import UserError


class BusinessCategoryImport(models.TransientModel):
    """Wizard para importar categorías de comercio masivamente."""

    _name = "business.category.import"
    _description = "Importar Categorías de Comercio"

    import_data = fields.Text(
        string="Datos a Importar",
        required=True,
        help="""Pegue aquí la lista de categorías.

Formato esperado:
- Las líneas que comienzan con 2 espacios son categorías padre.
- Las líneas sin espacios iniciales son subcategorías del padre anterior.

También acepta formato Markdown: [Nombre](url_ignorada)

Ejemplo:
  Alimentación
Panadería
Frutería
  Comercio
Ferretería
""",
    )

    def _parse_line(self, line: str) -> tuple[str, bool]:
        """
        Parsea una línea y devuelve el nombre y si es categoría padre.

        Args:
            line: Línea de texto a parsear.

        Returns:
            Tupla con (nombre_categoría, es_padre)
        """
        # Verificar si empieza con espacios (categoría padre)
        is_parent = line.startswith("  ") and not line.startswith("    ")

        # Limpiar espacios
        clean_line = line.strip()

        # Intentar extraer nombre del formato Markdown [Nombre](url)
        md_match = re.match(r"\[([^\]]+)\]\([^)]*\)", clean_line)
        if md_match:
            name = md_match.group(1).strip()
        else:
            name = clean_line

        return name, is_parent

    def action_import(self) -> dict:
        """
        Procesa la importación de categorías.

        Returns:
            Acción para mostrar las categorías importadas.
        """
        self.ensure_one()

        if not self.import_data:
            raise UserError("No hay datos para importar.")

        category_model = self.env["business.category"]
        created_categories: list[int] = []
        current_parent = None
        current_parent_name = ""

        lines = self.import_data.split("\n")

        for line in lines:
            # Ignorar líneas vacías
            if not line.strip():
                continue

            name, is_parent = self._parse_line(line)

            if not name:
                continue

            if is_parent:
                # Buscar o crear categoría padre
                existing = category_model.search([
                    ("name", "=", name),
                    ("parent_id", "=", False),
                ], limit=1)

                if existing:
                    current_parent = existing
                else:
                    current_parent = category_model.create({
                        "name": name,
                        "parent_id": False,
                    })
                    created_categories.append(current_parent.id)

                current_parent_name = name
            else:
                # Es subcategoría
                if not current_parent:
                    # Si no hay padre, crear como categoría raíz
                    existing = category_model.search([
                        ("name", "=", name),
                        ("parent_id", "=", False),
                    ], limit=1)

                    if not existing:
                        new_cat = category_model.create({
                            "name": name,
                            "parent_id": False,
                        })
                        created_categories.append(new_cat.id)
                else:
                    # Buscar si ya existe esta subcategoría
                    existing = category_model.search([
                        ("name", "=", name),
                        ("parent_id", "=", current_parent.id),
                    ], limit=1)

                    if not existing:
                        new_cat = category_model.create({
                            "name": name,
                            "parent_id": current_parent.id,
                        })
                        created_categories.append(new_cat.id)

        # Retornar acción para mostrar categorías
        return {
            "name": f"Categorías Importadas ({len(created_categories)} nuevas)",
            "type": "ir.actions.act_window",
            "res_model": "business.category",
            "view_mode": "list,form",
            "domain": [("id", "in", created_categories)] if created_categories else [],
            "context": {"search_default_group_parent": 1},
        }
