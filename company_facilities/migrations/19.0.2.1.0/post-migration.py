# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULE = "company_facilities"

# The six entries 19.0.2.0.0 renamed. Renaming set the en_US source, and the
# Spanish stayed as it was.
RENAMED = [
    "facility_step_free_access",
    "facility_accessible_toilet",
    "facility_accessible_parking",
    "facility_free_wifi",
    "facility_air_conditioning",
    "facility_pets_welcome",
    "category_accessibility",
]

TABLES = {
    "company.facility": "company_facility",
    "company.facility.category": "company_facility_category",
}


def migrate(cr, version):
    """Let the .po refill the names 19.0.2.0.0 renamed.

    The previous migration set the en_US source and left it at that, which is
    only half a rename: Odoo imports a module's translations with
    `overwrite=False`, so an entry that already had Spanish keeps it. The
    catalogue came out reading "Aseo accesible" and "Se admiten mascotas" where
    the client's own words are "Baño adaptado" and "Espacio pet friendly" -- an
    English source nobody sees, and a Spanish label nobody asked for.

    Dropping every key but the source is what makes the .po the authority
    again. It is deliberately not a write of the Spanish here: the wording
    belongs in es.po, one place, and a migration that also carried it would be
    a second copy to keep in step.

    Raw SQL because the ORM has no "forget this translation" -- writing the
    field under a language context is what DESTROYS a source (2026-08-14, 2134
    records), and writing it without one only sets en_US, which is already
    right.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    limpiados = 0
    for xmlid in RENAMED:
        record = env.ref("%s.%s" % (MODULE, xmlid), raise_if_not_found=False)
        if not record:
            continue
        table = TABLES.get(record._name)
        if not table:
            continue
        cr.execute(
            """
            UPDATE %s
               SET name = jsonb_build_object('en_US', name->>'en_US')
             WHERE id = %%s
               AND name ? 'en_US'
            """
            % table,
            (record.id,),
        )
        limpiados += cr.rowcount
    _logger.info(
        "Traducciones antiguas retiradas de %s registros; los .po las repueblan",
        limpiados,
    )
