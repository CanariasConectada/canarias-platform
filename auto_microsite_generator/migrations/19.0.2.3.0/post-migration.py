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
The model method adds guards of its own so no single wrong datum can strip a
platform site: the site is an aggregated shop (``is_marketplace``), its
company OWNS one (the structural tie of the Admin Portal to the portal's
company, whatever either is called), or its company name is protected.

Being a one-off on production, the run is logged so it can be diffed against
what is expected there (207 deleted; 1, 12, 13, 14 and 198 spared): the
totals, one line per spared site with the guards that held, one line per
entry kept for a reason, and the ids of the sites that lost the entry.

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
    report = env["res.company"]._remove_microsite_directory_menus(
        zone_companies=zone_companies
    )
    _logger.info(
        "auto_microsite_generator: /comercio menu entry deleted from %s "
        "merchant microsites; %s platform sites spared (portal, zones and "
        "their companies' other sites), %s entries kept for a reason.",
        len(report["deleted"]),
        len(report["spared"]),
        len(report["kept"]),
    )
    for website_id, company_id, company_name, reasons in report["spared"]:
        _logger.info(
            "auto_microsite_generator: /comercio SPARED on website %s "
            "(company %s, %s): %s.",
            website_id,
            company_id,
            company_name,
            ", ".join(reasons),
        )
    for website_id, company_id, company_name, menu_id, reason in report["kept"]:
        _logger.info(
            "auto_microsite_generator: /comercio KEPT on website %s "
            "(company %s, %s), menu %s: %s.",
            website_id,
            company_id,
            company_name,
            menu_id,
            reason,
        )
    _logger.info(
        "auto_microsite_generator: /comercio deleted on website ids: %s",
        sorted(report["deleted"]),
    )
