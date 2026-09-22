# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Take the "Guía Local" dropdown back from every site that is not a zone.

19.0.2.1.0 gave the dropdown (Memoria Viva, Lugares de Interés, Reseñas) to
all 218 sites, the portal included. The client ruled on 2026-09-07 that it
must show on the commercial zone pages alone, so this script removes it from
the portal and from every merchant microsite, and leaves the three zone sites
exactly as they are.

Recognised by structure, never by label: the parent of the Lugares entry,
when that parent is a dropdown holding nothing but the platform's verticals.

The zone companies are read straight from the column rather than through the
ORM. A post-migration runs while the registry is still being built: this
module declares no dependency on ``zone_company_ownership`` (deliberately --
the model reaches it through ``hasattr`` at runtime), so at this point the
field it defines is not in the registry yet and asking the ORM for it answers
"no zones anywhere". The first cut of this script did exactly that and
removed nothing on all 211 production sites while reporting success. The
column is there whatever the load order is.

When the column does not exist at all -- ``zone_company_ownership`` was never
installed -- or no company is keyed, nothing is removed: the only thing worse
than leaving the dropdown on the portal would be stripping it from the three
sites it was made for.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _zone_company_ids(cr):
    """The ids of the companies standing for a commercial zone, from SQL.

    Empty when the column is absent or nothing is keyed; both read as
    "cannot tell", which the caller treats as "remove nothing".
    """
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'res_company' AND column_name = 'zone_company_key'"
    )
    if not cr.fetchone():
        return []
    cr.execute("SELECT id FROM res_company WHERE zone_company_key IS NOT NULL")
    return [row[0] for row in cr.fetchall()]


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    zone_companies = env["res.company"].browse(_zone_company_ids(cr))
    removed = env["res.company"]._remove_local_guide_dropdowns(
        zone_companies=zone_companies
    )
    _logger.info(
        "auto_microsite_generator: Guía Local dropdown removed from %s non-zone "
        "sites (%s zone sites spared).",
        removed,
        len(zone_companies),
    )
