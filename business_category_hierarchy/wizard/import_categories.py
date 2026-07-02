# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import fields, models
from odoo.exceptions import UserError

# Markdown link: [Name](ignored url)
MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


class BusinessCategoryImport(models.TransientModel):
    _name = "business.category.import"
    _description = "Import Business Categories"

    import_data = fields.Text(
        string="Data to Import",
        required=True,
        help="Paste the category list here.\n\n"
        "Lines starting with 2 spaces are root categories; lines without "
        "leading spaces are subcategories of the previous root. Markdown "
        "links ([Name](url)) are also accepted.\n\n"
        "Example:\n"
        "  Alimentación\n"
        "Panadería\n"
        "Frutería\n"
        "  Comercio\n"
        "Ferretería",
    )

    def _parse_line(self, line):
        """Return (category name, is_root) for one line of input."""
        is_root = line.startswith("  ") and not line.startswith("    ")
        clean_line = line.strip()
        markdown_match = MARKDOWN_LINK.match(clean_line)
        name = markdown_match.group(1).strip() if markdown_match else clean_line
        return name, is_root

    def _get_or_create(self, name, parent, created_ids):
        category_model = self.env["business.category"]
        category = category_model.search(
            [("name", "=", name), ("parent_id", "=", parent.id if parent else False)],
            limit=1,
        )
        if not category:
            category = category_model.create(
                {"name": name, "parent_id": parent.id if parent else False}
            )
            created_ids.append(category.id)
        return category

    def action_import(self):
        self.ensure_one()
        if not self.import_data:
            raise UserError(self.env._("There is no data to import."))
        created_ids = []
        current_root = None
        for line in self.import_data.splitlines():
            if not line.strip():
                continue
            name, is_root = self._parse_line(line)
            if not name:
                continue
            if is_root:
                current_root = self._get_or_create(name, None, created_ids)
            else:
                self._get_or_create(name, current_root, created_ids)
        return {
            "name": self.env._("Imported Categories (%s new)", len(created_ids)),
            "type": "ir.actions.act_window",
            "res_model": "business.category",
            "view_mode": "list,form",
            "domain": [("id", "in", created_ids)],
            "context": {"search_default_group_parent": 1},
        }
