# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo.tools.sql import column_exists

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Say which shops change on the website when the switch goes away.

    19.0.3.0.0 drops ``res.company.facility_block_enabled``: the section now
    shows exactly when a shop has ticked something (client feedback,
    2026-09-15). Nothing is written and nothing is dropped -- the ORM leaves
    the orphan column alone, and that is fine. The only shops whose page
    changes are the ones that had the switch OFF while having items ticked:
    their section appears now. Logged so the change is on record, not a
    surprise.
    """
    if not column_exists(cr, "res_company", "facility_block_enabled"):
        return
    cr.execute(
        """
        SELECT c.id, c.name
          FROM res_company c
         WHERE c.facility_block_enabled IS NOT TRUE
           AND EXISTS (SELECT 1 FROM res_company_facility_rel r
                        WHERE r.company_id = c.id)
        """
    )
    rows = cr.fetchall()
    if rows:
        _logger.info(
            "Sección de instalaciones: %d comercios la tenían apagada con "
            "elementos marcados y pasan a mostrarla: %s",
            len(rows),
            ", ".join("%s (%s)" % (name, cid) for cid, name in rows),
        )
    else:
        _logger.info(
            "Sección de instalaciones: ningún comercio cambia de aspecto al "
            "retirar el interruptor"
        )
