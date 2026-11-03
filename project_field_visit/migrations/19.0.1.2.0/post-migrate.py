# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Let the platform administrators see the field visits right after deploy.

Until now only the built-in superuser and admin had the manager access, so
the owner never saw the menus. Same step as the install-time function in
``data/field_visit_admin_access.xml``; it does nothing once somebody was
appointed by hand.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    granted = env["project.project"]._field_visit_grant_admins()
    _logger.info(
        "Field visit manager access granted to %s administrator(s)", len(granted)
    )
