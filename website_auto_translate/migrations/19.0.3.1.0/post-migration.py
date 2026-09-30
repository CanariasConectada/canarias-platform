# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """File every sentence already listed under its site and its page title.

    The rows created by 19.0.3.0.0 carry the *view* name, which is neither the
    page title a visitor reads nor unique across sites. Five different
    homepages answered to "Inicio" and were shown as one heading of 123
    sentences, so the portal home looked absent while it was buried in the
    pile. Re-syncing rewrites ``website_id``, ``page_name`` and ``page_url``
    without touching a single translation: the rows are matched by the hash of
    their source term, and a correction lives on the term, not on the label.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    pages = env["auto.translate.job"].search(
        [("model_name", "=", "ir.ui.view")], order="id"
    )
    if not pages:
        return

    relabelled = 0
    for page in pages:
        try:
            with cr.savepoint():
                relabelled += len(page._sync_terms())
        except (
            Exception
        ) as error:  # noqa: BLE001 - one bad page must not stop the upgrade
            _logger.warning(
                "website_auto_translate: no se pudo reetiquetar %s(%s) [%s]: %s",
                page.model_name,
                page.res_id,
                page.lang,
                error,
            )

    _logger.info(
        "website_auto_translate: %s frases reetiquetadas con su sitio y su "
        "título de página",
        relabelled,
    )
