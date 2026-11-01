# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """One catalogue of microsite items per certification type.

    Sets the default headings where empty, links the seeded items to the
    question that backs them, and turns the deprecated positive items into
    catalogue items. Every step fills only what is empty: safe to re-run.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    counts = env["certification.highlight"]._cc_migrate_catalogue()
    _logger.info("Certification items catalogue migrated: %s", counts)
