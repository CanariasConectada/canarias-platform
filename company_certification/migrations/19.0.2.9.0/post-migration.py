# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Move the seals from above the footer into each merchant homepage.

    The imported homepages now call ``certification_block`` themselves, right
    before their contact section (and so right after the facilities); the
    layout-level section stays silent on them.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    counts = env["website"]._cc_place_seals_in_homepage()
    _logger.info("Certification seals placed in merchant homepages: %s", counts)
