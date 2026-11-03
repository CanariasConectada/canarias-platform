# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Opening hours as rows, and a homepage that reads them.

    1. Every company whose compact text parses gets its opening rows
       (``microsite.opening.slot``); the text is regenerated from them in
       the canonical form. A text the parser refuses keeps its text and is
       listed in the log: the merchant redoes it in the new editor.
    2. The static hours card the 2026 importer baked into the legacy
       homepages is swapped for the dynamic card template, so the hours a
       merchant saves finally reach the page (2026-09-15: "No se modifican
       los datos en la web aunque los modifiques aquí").

    Both steps are idempotent, so re-running the upgrade is safe.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Company = env["res.company"]

    with_text = Company.search([("microsite_opening_hours", "!=", False)])
    synced, unparsed = with_text._sync_slots_from_text()
    _logger.info(
        "Opening hours: %d companies carried a text, %d got their rows, "
        "%d already had rows, %d did not parse.",
        len(with_text),
        len(synced),
        len(with_text) - len(synced) - len(unparsed),
        len(unparsed),
    )
    if unparsed:
        _logger.warning(
            "Opening hours kept as free text (merchant to redo in the editor) "
            "for %d companies: ids %s",
            len(unparsed),
            unparsed.ids,
        )

    relinked = Company.search([])._relink_legacy_opening_hours_card()
    _logger.info(
        "Opening hours: the legacy homepage card now reads the company on "
        "%d sites (ids %s).",
        len(relinked),
        relinked.ids,
    )
