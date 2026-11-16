# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

"""The words the shop filters are made of.

Attributes, attribute values and tags carry no company: the same "Talla / M /
Sin gluten" is the sidebar of every website, so they are in scope as soon as
anybody is opted in. They were missed because nobody thinks of a filter as
content -- and yet they are the first words a visitor reads on ``/shop``.
"""

from odoo import models


class ProductAttribute(models.Model):
    _name = "product.attribute"
    _inherit = ["product.attribute", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["name"]


class ProductAttributeValue(models.Model):
    _name = "product.attribute.value"
    _inherit = ["product.attribute.value", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["name"]


class ProductTag(models.Model):
    _name = "product.tag"
    _inherit = ["product.tag", "auto.translate.mixin"]

    def _auto_translate_fields(self):
        return ["name"]
