# -*- coding: utf-8 -*-
"""Pre-migration 19.0.1.3.0 — sin operaciones requeridas."""
import logging
_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    _logger.info("ZCA pre-migration %s: ok (no-op)", version)
