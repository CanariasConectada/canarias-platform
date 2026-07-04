# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Create directory entries for the companies existing at install time.

    Without this, a fresh install would only list companies created or
    edited AFTER the module installation (the sync runs on create/write).
    """
    companies = env["res.company"].search([])
    companies._sync_to_directory_entry()
    _logger.info(
        "website_directory: synchronized %s existing companies", len(companies)
    )
