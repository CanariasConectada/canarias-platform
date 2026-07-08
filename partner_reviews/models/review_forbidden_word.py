# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

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
        """Return the forbidden words of ``self`` found inside ``text``."""
        if not text:
            return self.browse()
        lowered = text.lower()
        return self.filtered(lambda word: word.name.lower() in lowered)
