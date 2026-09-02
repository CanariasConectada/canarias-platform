# Copyright 2026 Canarias Conectada
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).

from odoo import models


class ProductPublicCategory(models.Model):
    _inherit = "product.public.category"

    def _shop_twin_categories(self):
        """Every sibling category rendered under the same visible name.

        The migration left each merchant with their own copy of the everyday
        category names -- twelve "Entrantes", nine "Ensaladas" -- so the
        marketplace sidebar showed the same word over and over, and picking
        one of them silently filtered down to a single merchant's plates.
        The sidebar collapses twins into one entry and the shop domain
        expands a picked category to all of them, so "Entrantes" means
        entrantes, not "the entrantes of whoever created category 80".

        Compared in Python rather than with ``=ilike``: the name is data
        merchants type, and a ``%`` or ``_`` in it would silently widen an
        SQL pattern. Siblings only (same parent), so a subcategory can still
        share a name with an unrelated top-level one without being merged.
        """
        self.ensure_one()
        key = (self.name or "").strip().casefold()
        siblings = self.search([("parent_id", "=", self.parent_id.id)])
        return siblings.filtered(
            lambda c: (c.name or "").strip().casefold() == key
        )
