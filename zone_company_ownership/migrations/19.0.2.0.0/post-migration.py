# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Take the zone companies back off the merchants' allowed companies.

Until 19.0.1.1.0 a merchant's user account was given their zone company along
with their own, the same way their products were. On the products that is the
whole point -- it is what lists them in the zone shop. On the user account it
is a cross-tenant hole: ``res.users.company_ids`` is what every multi-company
record rule reads, so the zone company did not mean "my catalogue is in the
zone shop", it meant "I may read and write everything the zone owns".

Measured on the live database before this ran: a Guanarteme merchant whose own
shop holds 57 products could read 1175 of them and had write access to another
merchant's product, plus 88 contacts instead of their own 10.

Only two populations keep a zone company, and the guard in
``res.users._zone_company_holders`` is the single definition of who they are:
the staff OF a zone (their own company IS the zone) and the system
administrators. Merchants holding ``base.group_multi_company`` are NOT exempt
-- they are the population being fixed.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    zones = env["res.company"]._zone_companies()
    if not zones:
        _logger.info("zone_company_ownership: no zone companies, nothing to do.")
        return

    # ``active_test=False`` on purpose: an archived account still holds its
    # companies, and unarchiving it later would bring the hole straight back.
    users = (
        env["res.users"]
        .with_context(active_test=False)
        .search([("company_ids", "in", zones.ids)])
    )
    changed = users._drop_zone_companies()
    _logger.info(
        "zone_company_ownership: %s of %s users holding a zone company were "
        "stripped of it; %s kept it (zone staff and administrators).",
        len(changed),
        len(users),
        len(users) - len(changed),
    )
