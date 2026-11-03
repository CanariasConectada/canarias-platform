# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Fill the microsite status of the field-visit tasks that already exist.

Tasks imported before this version have no status until the daily cron
runs; one batched check at upgrade fills it right away.
"""

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    tasks = env["project.task"].search(
        [("is_field_visit_project", "=", True), ("business_company_id", "!=", False)]
    )
    tasks._field_visit_refresh_microsite_status()
    _logger.info("Microsite status filled on %s field-visit tasks.", len(tasks))
