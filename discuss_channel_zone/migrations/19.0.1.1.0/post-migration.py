# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)

MODULE = "discuss_channel_zone"

# The descriptions 19.0.1.0.0 seeded, as they should read. The database holds
# them with the XML indentation that came along with the data file.
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
    """Strip the XML indentation from the four seeded descriptions.

    Only descriptions nobody edited since they were seeded (same text once
    whitespace is collapsed) are rewritten. The columns are plain
    ``varchar``/``text``: this version translates the seeded channels at
    display time and needs no schema change.
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
    fixed = 0
    for xmlid, clean in SEEDED_DESCRIPTIONS.items():
        channel_id = seeded.get(xmlid)
        if not channel_id:
            continue
        cr.execute(
            "SELECT description::text FROM discuss_channel WHERE id = %s",
            (channel_id,),
        )
        row = cr.fetchone()
        if row and row[0] and row[0] != clean and _normalise(row[0]) == clean:
            cr.execute(
                "UPDATE discuss_channel SET description = %s WHERE id = %s",
                (clean, channel_id),
            )
            fixed += 1
    _logger.info("discuss_channel_zone: %s seeded descriptions cleaned", fixed)
