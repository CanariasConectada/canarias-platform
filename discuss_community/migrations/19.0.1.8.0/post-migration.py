# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Bring every community member to the community profile.

    Since 19.0.1.8.0 registered residents get the same profile as guests
    (``res.users._is_community_member``: the community group, never
    administrators, merchants or zone managers). This removes their seats in
    the staff channels ("general", "Administrators" and any channel
    restricted to employees), takes them out of their OdooBot DM and disables
    OdooBot for them. The logic lives on the model
    (``_cleanup_community_members``) so it is tested like any other code
    path; this script only runs it once. Idempotent.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    counters = env["res.users"]._cleanup_community_members()
    _logger.info("discuss_community 19.0.1.8.0: member cleanup %s", counters)
