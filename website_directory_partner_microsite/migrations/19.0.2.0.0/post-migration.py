# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Queue a full directory resync so the 75 legal-name cards pick up the
trade name the new hook now serves. Async on purpose: the sync cron
already processes pending companies in batches inside savepoints."""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    companies = (
        env["res.company"]
        .with_context(active_test=False)
        .search([("show_in_directory", "=", True)])
    )
    companies.write({"directory_sync_pending": True})
    _logger.info(
        "website_directory_partner_microsite: %s companies queued for a "
        "directory resync (trade names).",
        len(companies),
    )
