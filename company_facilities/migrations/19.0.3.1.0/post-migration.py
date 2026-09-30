# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Move the facilities block from above the footer into each homepage.

    The ``layout_facilities`` hook is gone with this version (the record is
    dropped by the module update); the imported homepages now call the block
    themselves, right before their contact section.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    counts = env["website"]._cf_place_facilities_in_homepage()
    _logger.info("Facilities block placed in merchant homepages: %s", counts)
