# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from odoo import fields, models


class ReviewForbiddenWord(models.Model):
    """Words that send a review to manual moderation when found.

    Kept as a dedicated model (instead of a config parameter) so moderators
    can maintain the list from the backend without technical knowledge, and
    so words can be archived instead of deleted.
    """

    _name = "review.forbidden.word"
    _description = "Review Forbidden Word"
    _order = "name"

    name = fields.Char(string="Word", required=True, index=True)
    active = fields.Boolean(default=True)

    _name_uniq = models.Constraint(
        "unique(name)",
        "This word is already in the forbidden list.",
    )

    def _match(self, text):
        """Return the forbidden words of ``self`` found inside ``text``.

        The match is anchored on word boundaries over the lower-cased text,
        not a raw substring: this avoids flagging legitimate words that merely
        contain a forbidden one (``especialista`` must not match ``cialis``)
        and the trivial evasion that a substring check invites. ``re.escape``
        keeps entries with regex metacharacters literal.
        """
        if not text:
            return self.browse()
        normalized = text.lower()
        return self.filtered(
            lambda word: re.search(
                r"\b" + re.escape(word.name.lower()) + r"\b", normalized
            )
        )
