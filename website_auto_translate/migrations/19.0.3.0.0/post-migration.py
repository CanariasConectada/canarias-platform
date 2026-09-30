# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """List the sentences of every page already in the queue.

    Without this the new screen is empty until each page happens to be
    translated again, and the whole point of it is to let somebody read what
    the machine has *already* written -- 162 pages of it, in four languages.

    The three pages locked by hand are unlocked at field level on the way
    through. Their sentences are created locked, so nothing anybody typed is
    at risk; what changes is that the other thirty-odd sentences on those
    pages stop being frozen along with the one that was corrected.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Job = env["auto.translate.job"]
    pages = Job.search([("model_name", "=", "ir.ui.view")], order="id")
    if not pages:
        return

    built = sentences = 0
    for page in pages:
        try:
            with cr.savepoint():
                terms = page._sync_terms()
        except (
            Exception
        ) as error:  # noqa: BLE001 - one bad page must not stop the upgrade
            _logger.warning(
                "website_auto_translate: no se pudieron listar las frases de "
                "%s(%s) [%s]: %s",
                page.model_name,
                page.res_id,
                page.lang,
                error,
            )
            continue
        if terms:
            built += 1
            sentences += len(terms)

    # Only now, so a page whose sentences could not be built keeps the lock it
    # already had rather than being handed back to the machine unprotected.
    freed = pages.filtered(lambda job: job.state == "locked" and job.term_ids)
    if freed:
        freed.write({"state": "done"})

    _logger.info(
        "website_auto_translate: %s páginas desglosadas en %s frases; "
        "%s pasan de bloqueo por página a bloqueo por frase",
        built,
        sentences,
        len(freed),
    )
