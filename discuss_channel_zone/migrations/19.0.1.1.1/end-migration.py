# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo.tools import sql

_logger = logging.getLogger(__name__)

COLUMNS = {"name": "varchar", "description": "text"}


def migrate(cr, version):
    """Put ``discuss_channel.name``/``description`` back to plain text columns.

    An unreleased build of this module made both fields translatable, which
    turned the columns into ``jsonb`` in the databases it was installed on
    (the lab, never production). Removing ``translate=True`` is NOT enough to
    undo that: the loader keeps treating a field as translated for as long
    as ``ir_model_fields.translate`` says so, re-patching the definition on
    every update. So the conversion is done here, explicitly, keeping the
    ``en_US`` value (the one every language fell back to), and the
    reflection is corrected so the loader stops re-patching.

    ``end`` script on purpose: it runs after every module of the update has
    initialised its models, so no later module step can convert the columns
    back while the stale reflection is still in memory.

    A no-op wherever the columns are already plain text (production).
    """
    if not version:
        return
    for column, column_type in COLUMNS.items():
        cr.execute(
            """
            SELECT udt_name FROM information_schema.columns
             WHERE table_name = 'discuss_channel' AND column_name = %s
            """,
            (column,),
        )
        row = cr.fetchone()
        if not row or row[0] != "jsonb":
            continue
        sql.convert_column_translatable(cr, "discuss_channel", column, column_type)
        _logger.info(
            "discuss_channel_zone: discuss_channel.%s converted back to %s",
            column,
            column_type,
        )
    cr.execute(
        """
        UPDATE ir_model_fields SET translate = NULL
         WHERE model = 'discuss.channel' AND name IN %s
           AND translate IS NOT NULL
        """,
        (tuple(COLUMNS),),
    )
