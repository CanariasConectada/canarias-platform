# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)

MODULE = "discuss_channel_zone"

# The descriptions 19.0.1.0.0 seeded, as they sit in the database: the XML
# indentation came along. Normalised before comparing, and replaced ONLY when
# nobody edited them since, so a description an administrator rewrote is
# never touched.
SEEDED_DESCRIPTIONS = {
    "channel_canarias": (
        "Community channel of the whole platform. "
        "Open to everyone, visitors included."
    ),
    "channel_guanarteme": (
        "Neighbourhood channel of Guanarteme. An account is required to take part."
    ),
    "channel_tamaraceite": (
        "Neighbourhood channel of Tamaraceite. An account is required to take part."
    ),
    "channel_lomolosfrailes": (
        "Neighbourhood channel of Lomo los Frailes. "
        "An account is required to take part."
    ),
}


def _normalise(text):
    return " ".join((text or "").split())


def migrate(cr, version):
    """Finish turning channel names and descriptions into translated fields.

    By the time this runs the ORM has already converted both columns to
    ``jsonb`` with every existing value under ``en_US`` (that is how Odoo
    upgrades a field to ``translate=True``). Two things are left:

    1. The four seeded descriptions lose the XML indentation they were stored
       with, in ``en_US`` (the source the ``.po`` files translate).
    2. Every OTHER channel gets its current text copied to ``es_ES``, the
       platform's main language, so the value is explicitly Spanish too and
       not just a fallback. The seeded channels are skipped on purpose: their
       Spanish (and French, German...) comes from the module's ``.po`` files,
       which only fill languages a record does not have yet.
    """
    if not version:
        return
    cr.execute(
        """
        SELECT name, res_id FROM ir_model_data
         WHERE module = %s AND model = 'discuss.channel'
        """,
        (MODULE,),
    )
    seeded = dict(cr.fetchall())

    for xmlid, clean in SEEDED_DESCRIPTIONS.items():
        channel_id = seeded.get(xmlid)
        if not channel_id:
            continue
        cr.execute(
            "SELECT description->>'en_US' FROM discuss_channel WHERE id = %s",
            (channel_id,),
        )
        row = cr.fetchone()
        if row and row[0] and row[0] != clean and _normalise(row[0]) == clean:
            cr.execute(
                """
                UPDATE discuss_channel
                   SET description = description || jsonb_build_object('en_US', %s)
                 WHERE id = %s
                """,
                (clean, channel_id),
            )

    skip = tuple(seeded.values()) or (0,)
    for column in ("name", "description"):
        cr.execute(
            f"""
            UPDATE discuss_channel
               SET {column} = {column}
                   || jsonb_build_object('es_ES', {column}->>'en_US')
             WHERE {column} IS NOT NULL
               AND {column} ? 'en_US'
               AND NOT {column} ? 'es_ES'
               AND id NOT IN %s
            """,
            (skip,),
        )
        _logger.info(
            "discuss_channel_zone: %s channel %ss copied to es_ES",
            cr.rowcount,
            column,
        )
