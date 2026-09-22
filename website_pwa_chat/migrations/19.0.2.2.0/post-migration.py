# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

MODULE = "website_pwa_chat"
SOURCE_LANG = "es_ES"
BASE_LANG = "en_US"


def migrate(cr, version):
    """Give the Spanish source its own key before an en.po can overwrite it.

    This module's templates are written in Spanish, and Odoo keeps ``en_US`` as
    the technical *base* of every translatable jsonb column: the value any
    language without an entry of its own falls back to. Shipping an ``en.po``
    therefore writes English over the Spanish source, and unless Spanish owns a
    key of its own by then, the Spanish is simply gone. That is not a
    hypothetical -- it is what cost 2134 records their Spanish on 2026-08-14,
    through the automatic translator rather than a .po, but by exactly this
    mechanism.

    The timing is the whole point, and it is why this is a *post*-migration
    rather than a hook. Odoo's module loader runs, in order:

        load_data (the XML)  ->  post-migration  ->  translations  ->  post_init_hook

    so this is the last moment at which ``en_US`` still holds the Spanish that
    the XML just wrote, and the first at which the records exist. A
    ``post_init_hook`` would run after the ``en.po`` had already landed.

    Known gap, stated plainly: migrations do not run on a *fresh* install, so a
    brand-new database installs this module, loads the en.po and shows the
    Spanish strings in English until it is upgraded. Every existing database --
    production and every copy of it -- goes through this path.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    installed = [code for code, _ in env["res.lang"].get_installed()]
    if SOURCE_LANG not in installed or SOURCE_LANG == BASE_LANG:
        return

    cr.execute("SELECT DISTINCT model FROM ir_model_data WHERE module = %s", (MODULE,))
    for (model_name,) in cr.fetchall():
        if model_name not in env:
            continue
        model = env[model_name]
        if model._abstract or model._transient:
            continue
        for field in model._fields.values():
            if not field.translate or not field.store or not field.column_type:
                continue
            column = SQL.identifier(field.name)
            cr.execute(
                SQL(
                    """
                    UPDATE %s t
                       SET %s = jsonb_set(t.%s, %s, t.%s -> %s)
                      FROM ir_model_data d
                     WHERE d.module = %s
                       AND d.model = %s
                       AND d.res_id = t.id
                       AND t.%s ? %s
                       AND NOT t.%s ? %s
                    """,
                    SQL.identifier(model._table),
                    column,
                    column,
                    [SOURCE_LANG],
                    column,
                    BASE_LANG,
                    MODULE,
                    model_name,
                    column,
                    BASE_LANG,
                    column,
                    SOURCE_LANG,
                )
            )
            if cr.rowcount:
                _logger.info(
                    "%s: %s.%s -- %s registros conservan su %s antes del en.po",
                    MODULE,
                    model_name,
                    field.name,
                    cr.rowcount,
                    SOURCE_LANG,
                )
