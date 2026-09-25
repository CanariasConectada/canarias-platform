# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class DiscussChannel(models.Model):
    """Channel names and descriptions in the reader's language.

    The platform speaks seven languages and its community channels are read
    by residents and visitors in all of them, so the name and the topic of a
    channel are translatable like any other user-facing label.

    Upgrade path: the ORM converts the ``varchar``/``text`` columns to
    ``jsonb`` on its own when the field becomes translatable
    (``fields_textual._convert_db_column`` → ``convert_column_translatable``),
    keeping every existing value under ``en_US``; the 19.0.1.1.0 migration
    then copies it to ``es_ES`` and the module's ``.po`` files fill the other
    languages of the four seeded channels.

    Trade-off worth knowing: renaming a channel from Discuss changes the name
    in the language of the person renaming it only, exactly like renaming a
    product.
    """

    _inherit = "discuss.channel"

    name = fields.Char(translate=True)
    description = fields.Text(translate=True)
