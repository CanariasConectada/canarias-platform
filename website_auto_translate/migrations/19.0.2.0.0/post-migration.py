# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import SQL

_logger = logging.getLogger(__name__)

BASE_LANG = "en_US"


def migrate(cr, version):
    """Give the source language its own jsonb key on every record we manage.

    Until 19.0.2.0.0 the Spanish source lived only in ``en_US``, the technical
    base that every language without an entry of its own falls back to. English
    was also a translation target, so the run of 2026-08-14 wrote machine
    English over that base and the Spanish simply ceased to exist -- 1847
    records, recovered afterwards from a pre-run dump.

    Recovering the *text* was a restore job and is already done. This migration
    fixes the *shape*, so the records that were queued but never reached, and
    any that are re-queued later, cannot be destroyed the same way.

    Scoped to records this module actually has a job for. A blanket update
    would stamp ``es_ES`` onto thousands of core Odoo views whose base is
    genuinely English, freezing that English as their Spanish and fighting the
    ``.po`` files on the next module update.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    source_lang = (
        env["ir.config_parameter"]
        .sudo()
        .get_param("website_auto_translate.source_lang", "es_ES")
    )
    if source_lang == BASE_LANG:
        return

    for model_name in sorted(env.registry):
        model = env[model_name]
        # The mixin's own marker: no registry introspection needed, and it stays
        # correct when another model is added to the rollout later.
        if model._abstract or model._transient:
            continue
        if not hasattr(model, "_auto_translate_fields"):
            continue
        for field_name in model._auto_translate_fields():
            field = model._fields.get(field_name)
            if field is None or not field.translate or not field.store:
                continue
            column = SQL.identifier(field_name)
            cr.execute(
                SQL(
                    """
                    UPDATE %s t
                       SET %s = jsonb_set(t.%s, %s, t.%s -> %s)
                     WHERE t.%s ? %s
                       AND NOT t.%s ? %s
                       AND EXISTS (
                           SELECT 1 FROM auto_translate_job j
                            WHERE j.model_name = %s
                              AND j.field_name = %s
                              AND j.res_id = t.id
                       )
                    """,
                    SQL.identifier(model._table),
                    column,
                    column,
                    [source_lang],
                    column,
                    BASE_LANG,
                    column,
                    BASE_LANG,
                    column,
                    source_lang,
                    model_name,
                    field_name,
                )
            )
            if cr.rowcount:
                _logger.info(
                    "Auto translate: %s.%s -- %s registros recuperan su clave %s",
                    model_name,
                    field_name,
                    cr.rowcount,
                    source_lang,
                )
