# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Put the zone companies onto the contacts that predate the rule.

19.0.1.0.0 taught the catalogue to carry its owner's zone company; contacts
were left out, so a neighbourhood's address book could not be seen -- or
grouped -- as one. From 19.0.3.0.0 ``res.partner`` runs the same sync as
``product.template``; this script applies it once to everything the
zone-owning shops already own. The stored ``zone_company_ids`` fields are
recomputed by the update itself and need nothing from us.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    owners = (
        env["res.company"]
        .with_context(active_test=False)
        .search([("commercial_zone", "not in", (False, "canarias"))])
    )
    if not owners:
        _logger.info("zone_company_ownership: no zone-owning shops, nothing to do.")
        return
    changed = env["res.partner"]._sync_zone_companies_for_owners(owners)
    _logger.info(
        "zone_company_ownership: zone companies applied to %s contacts "
        "of %s shops.",
        len(changed),
        len(owners),
    )
