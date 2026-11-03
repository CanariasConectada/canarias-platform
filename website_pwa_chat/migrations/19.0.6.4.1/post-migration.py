# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Reload the Spanish translations of this module, overwriting.

    Until 19.0.6.4.1 `i18n/es.po` held only the Discuss dialog strings. The
    website support bubble was therefore never translated to Spanish, and its
    Spanish value ended up as the English text of `i18n/en.po` ("Close the
    chat", "Talk to support"). A regular update keeps any value that differs
    from the source term as an "existing translation", so the fixed file alone
    would not replace those English words. Spanish is this module's source
    language, so overwriting es_ES from the file cannot lose anything.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env["res.lang"]._lang_get("es_ES"):
        return
    env["ir.module.module"]._load_module_terms(
        ["website_pwa_chat"], ["es_ES"], overwrite=True
    )
    _logger.info("website_pwa_chat: es_ES translations reloaded with overwrite")
