# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Take the ``/comercio`` top-menu entry off every merchant microsite.

Client ruling, 2026-09-21: a visitor who is inside a shop's microsite is not
invited out to the directory of all the other shops. The "Zonas Comerciales"
dropdown stays as the way out, and so do Home and Shop. The portal and the
three zone sites keep their entry, and the ``/comercio`` route itself keeps
answering on every host -- only the menu entry goes.

Measured on production the same day: 212 entries, one per website, every one
of them url ``/comercio`` exactly (no trailing slash, no language prefix), a
direct child of its site's root menu, childless. Five sit on sites that are
not a merchant's and stay: the portal (1), the zones (12, 13, 14) and the
platform company's Admin Portal (198).

The zone companies are read straight from the column, for the reason the
19.0.2.2.0 script spells out: ``zone_company_ownership`` is not in the
registry yet while this runs, and the ORM would answer "no zones anywhere".
The model method adds two guards of its own (the protected company names and
``is_marketplace``) so no single wrong datum can strip the portal or a zone.

19.0.2.1.0 restored this very entry on the sites that missed it. It only
runs on a database coming from before 19.0.2.1.0, and then BEFORE this
script, so what it restores on a merchant site is taken off again here.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def _zone_company_ids(cr):
    """The ids of the companies standing for a commercial zone, from SQL.

    Empty when the column is absent or nothing is keyed; both read as
    "cannot tell", which the model method treats as "remove nothing".
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
    counts = env["res.company"]._remove_microsite_directory_menus(
        zone_companies=zone_companies
    )
    _logger.info(
        "auto_microsite_generator: /comercio menu entry deleted from %s "
        "merchant microsites; %s kept on platform sites (portal, zones), "
        "%s kept because not top-level, %s kept because they have children.",
        counts["deleted"],
        counts["spared_platform_site"],
        counts["skipped_not_top_level"],
        counts["skipped_has_children"],
    )
