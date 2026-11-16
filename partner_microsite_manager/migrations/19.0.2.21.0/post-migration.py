# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo.tools import SQL

_logger = logging.getLogger(__name__)

BASE_LANG = "en_US"
SOURCE_PARAM = "website_auto_translate.source_lang"

# The merchant texts that became translatable in 19.0.2.21.0.
TRANSLATED_FIELDS = (
    "microsite_button_text",
    "microsite_intro_title",
    "microsite_banner_title",
    "microsite_about_title",
    "microsite_about_text",
    "microsite_services_title",
    "microsite_services_text",
    "microsite_parking_info",
    "microsite_delivery_info",
)


def _is_jsonb(cr, field_name):
    cr.execute(
        """
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'res_company' AND column_name = %s
        """,
        [field_name],
    )
    row = cr.fetchone()
    return bool(row) and row[0] == "jsonb"


def _source_lang(cr):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = %s", [SOURCE_PARAM])
    row = cr.fetchone()
    return row[0] if row and row[0] else "es_ES"


def _stamp_source_key(cr, field_name, source_lang):
    """Give the Spanish its own jsonb key.

    Odoo converts a plain column into ``{"en_US": <text>}``. Spanish renders
    fine from there (any language without a key falls back to ``en_US``), but
    the first machine English written to the base would replace it. The same
    trap that cost 1847 records on 2026-08-14: the source owns its key from
    day one.
    """
    column = SQL.identifier(field_name)
    cr.execute(
        SQL(
            """
            UPDATE res_company
               SET %s = jsonb_set(%s, %s, %s -> %s)
             WHERE %s ? %s AND NOT %s ? %s
            """,
            column,
            column,
            [source_lang],
            column,
            BASE_LANG,
            column,
            BASE_LANG,
            column,
            source_lang,
        )
    )
    return cr.rowcount


def _queue_existing_texts(cr, field_name, source_lang):
    """Queue today's non-empty texts of the opted-in shops, once.

    Plain SQL on purpose: the jobs must be created whatever order
    ``website_auto_translate`` and this module load in during the same
    upgrade, and the ORM model of the former may not be in the registry yet.
    Idempotent: a row that already exists is left exactly as it is.
    """
    cr.execute(
        """
        SELECT code FROM res_lang WHERE active AND code <> %s ORDER BY code
        """,
        [source_lang],
    )
    langs = [row[0] for row in cr.fetchall()]
    if not langs:
        return 0
    cr.execute(
        SQL(
            """
            INSERT INTO auto_translate_job
                   (model_name, res_id, field_name, lang, state, attempts,
                    content_kind, create_uid, write_uid, create_date, write_date)
            SELECT 'res.company', c.id, %s, l.code, 'pending', 0,
                   'shop', 1, 1, now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
              FROM res_company c
             CROSS JOIN unnest(%s::varchar[]) AS l(code)
             WHERE c.auto_translate_enabled
               AND COALESCE(c.%s ->> %s, '') <> ''
            ON CONFLICT (model_name, res_id, field_name, lang) DO NOTHING
            """,
            field_name,
            langs,
            SQL.identifier(field_name),
            source_lang,
        )
    )
    return cr.rowcount


def migrate(cr, version):
    """Keep the Spanish, then hand the existing texts to the translator.

    1. Stamp ``es_ES`` on every converted column (always: it protects the
       source even when the translator is not installed yet).
    2. When ``website_auto_translate`` is installed and the shop opted in,
       queue one job per non-empty text and target language, so the shops
       that were written before today get translated too.
    """
    if not version:
        return
    source_lang = _source_lang(cr)
    columns = [name for name in TRANSLATED_FIELDS if _is_jsonb(cr, name)]
    if source_lang != BASE_LANG:
        for name in columns:
            stamped = _stamp_source_key(cr, name, source_lang)
            if stamped:
                _logger.info(
                    "partner_microsite_manager: res_company.%s -- %s textos "
                    "guardan su clave %s",
                    name,
                    stamped,
                    source_lang,
                )

    cr.execute("SELECT to_regclass('auto_translate_job')")
    has_queue = cr.fetchone()[0] is not None
    cr.execute(
        """
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'res_company' AND column_name = 'auto_translate_enabled'
        """
    )
    opted_in_column = bool(cr.fetchone())
    if not (has_queue and opted_in_column):
        return
    queued = 0
    for name in columns:
        queued += _queue_existing_texts(cr, name, source_lang)
    _logger.info(
        "partner_microsite_manager: %s trabajos de traduccion encolados "
        "para los textos existentes",
        queued,
    )
