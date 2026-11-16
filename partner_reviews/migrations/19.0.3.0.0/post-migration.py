# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Move the review forbidden words into the shared platform list.

``review.forbidden.word`` is replaced by ``moderation.forbidden.word``
(module ``website_moderation_forbidden_word``, already installed as a
dependency when this script runs). Every row of the old table is copied,
skipping the entries the shared seed already holds (compared on the
accent-folded form) but propagating the old row's ``active`` state onto
them: a word an administrator had switched off stays off, and a word that
held reviews yesterday keeps holding them today even where the seed ships
it archived by default (``timo``). The archived-by-default seed rows only
apply where the old list did not have the word.

Odoo drops the ``ir.model`` of the removed model at the end of the update
but leaves both the table and the ``noupdate`` xmlids of its rows behind,
so both are removed here once the copy is done.
"""
import logging

from odoo import SUPERUSER_ID, api
from odoo.tools import sql

from odoo.addons.website_moderation_forbidden_word.models.moderation_forbidden_word import (  # noqa: E501
    normalize_text,
)

_logger = logging.getLogger(__name__)

# Static identifiers of the removed model, interpolated into the SQL below
# as-is: they are constants of this file, never user data.
OLD_TABLE = "review_forbidden_word"
OLD_MODEL = "review.forbidden.word"


def migrate(cr, version):
    if not version or not sql.table_exists(cr, OLD_TABLE):
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Word = env["moderation.forbidden.word"].with_context(active_test=False)
    cr.execute(f"SELECT name, active FROM {OLD_TABLE} ORDER BY id")
    copied = flipped = skipped = 0
    for name, active in cr.fetchall():
        normalized = normalize_text(name)
        if not normalized:
            continue
        existing = Word.search([("name_normalized", "=", normalized)], limit=1)
        if existing:
            skipped += 1
            if existing.active != bool(active):
                existing.active = bool(active)
                flipped += 1
            continue
        Word.create(
            {
                "name": name,
                "active": bool(active),
                "note": "Migrated from the merchant reviews list",
            }
        )
        copied += 1
    cr.execute("DELETE FROM ir_model_data WHERE model = %s", (OLD_MODEL,))
    cr.execute(f"DROP TABLE {OLD_TABLE}")
    _logger.info(
        "partner_reviews: %s review forbidden word(s) copied into the shared "
        "list, %s already there (%s switched to the old active state), old "
        "table dropped.",
        copied,
        skipped,
        flipped,
    )
