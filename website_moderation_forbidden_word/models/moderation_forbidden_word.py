# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re
import unicodedata

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Private-use code point that shields the enye from the accent folding:
# NFKD decomposes "ñ" into "n" + tilde, and dropping the tilde would turn
# "coño" into "cono" (a cone) and flag every ice-cream review. Vowels lose
# their accents, the enye keeps its identity.
_ENYE_SENTINEL = ""


def normalize_text(text):
    """Lower-case, accent-folded, whitespace-collapsed form of ``text``.

    Both the stored words and the texts they are searched in go through
    this function, so ``IMBÉCIL``, ``imbecil`` and ``Imbécil`` are the same
    word. Repeated letters (``imbeeecil``) or symbol substitutions
    (``imb3cil``) are NOT tolerated: a predictable, explainable rule beats
    a clever one that moderators cannot reason about.
    """
    if not text:
        return ""
    folded = " ".join(text.lower().split()).replace("ñ", _ENYE_SENTINEL)
    folded = unicodedata.normalize("NFKD", folded)
    folded = "".join(char for char in folded if not unicodedata.combining(char))
    return folded.replace(_ENYE_SENTINEL, "ñ")


class ModerationForbiddenWord(models.Model):
    """Administrator-managed word list shared by every moderated text.

    Consumers (merchant reviews, local content comments...) only need the
    two matcher helpers, always called through ``sudo()`` because the list
    is readable by administrators only:

    * :meth:`_find_matches` returns the entries found in a text;
    * :meth:`_contains_forbidden` is the boolean shortcut.
    """

    _name = "moderation.forbidden.word"
    _description = "Moderation Forbidden Word"
    _order = "name_normalized"
    _rec_name = "name"

    name = fields.Char(
        string="Word",
        required=True,
        help="A single word or a whole expression (e.g. 'hijo de puta'). "
        "Matching ignores case and accents and only hits whole words: "
        "'imbécil' flags 'IMBECIL' but not 'imbecilidad'.",
    )
    name_normalized = fields.Char(
        string="Normalized Form",
        compute="_compute_name_normalized",
        store=True,
        index=True,
        help="Technical: lower-case, accent-folded form used for matching "
        "and uniqueness.",
    )
    active = fields.Boolean(default=True)
    note = fields.Char(
        help="Optional reason or context for moderators (why the word is "
        "listed, false positives to watch for...)."
    )

    _name_normalized_uniq = models.Constraint(
        "unique(name_normalized)",
        "This word is already in the forbidden list (case and accents do "
        "not make a different word).",
    )

    @api.depends("name")
    def _compute_name_normalized(self):
        for word in self:
            word.name_normalized = normalize_text(word.name)

    @api.constrains("name")
    def _check_name(self):
        """An entry needs at least one word character once normalized.

        Punctuation-only entries ("...", "!!!") would never anchor on a
        word boundary and only confuse whoever reads the list.
        """
        for word in self:
            if not re.search(r"\w", normalize_text(word.name)):
                raise ValidationError(
                    _("A forbidden word must contain at least one letter or digit.")
                )

    # ------------------------------------------------------------------
    # Matcher
    # ------------------------------------------------------------------
    @api.model
    def _normalize(self, text):
        """Model-level alias of :func:`normalize_text` for consumers."""
        return normalize_text(text)

    @api.model
    def _get_pattern(self):
        """One compiled regex over every active entry.

        Alternatives are sorted longest first so a multi-word entry wins
        over one of its own words, and wrapped in look-arounds instead of
        ``\\b`` so entries starting or ending with a non-word character
        (``100% gratis``, ``www``) still anchor on whole words. ``\\w`` is
        Unicode-aware, so the enye counts as a letter. An empty list yields
        a pattern that never matches, so callers can always pass the result
        down (``None`` means "not computed yet").

        Intentionally NOT cached (no ``ormcache``): a few hundred entries
        compile in microseconds, and an uncached pattern can never be stale
        across workers after an administrator edits the list. Batch callers
        compute it once and hand it to the matchers instead.
        """
        words = self.sudo().with_context(active_test=True).search([])
        normalized = sorted(
            {word.name_normalized for word in words if word.name_normalized},
            key=len,
            reverse=True,
        )
        if not normalized:
            return re.compile(r"(?!)")
        alternatives = "|".join(re.escape(word) for word in normalized)
        return re.compile(r"(?<!\w)(?:%s)(?!\w)" % alternatives)

    @api.model
    def _find_matches(self, text, pattern=None):
        """Sorted list of the active entries (``name``) found in ``text``.

        ``pattern`` is the result of :meth:`_get_pattern`; batch callers pass
        it so N texts cost one search and one compile.
        """
        if not text:
            return []
        if pattern is None:
            pattern = self._get_pattern()
        found = {match.group(0) for match in pattern.finditer(normalize_text(text))}
        if not found:
            return []
        words = self.sudo().search([("name_normalized", "in", list(found))])
        return sorted(words.mapped("name"))

    @api.model
    def _contains_forbidden(self, text, pattern=None):
        """Whether ``text`` contains at least one active forbidden word
        (``pattern`` as in :meth:`_find_matches`)."""
        if not text:
            return False
        if pattern is None:
            pattern = self._get_pattern()
        return bool(pattern.search(normalize_text(text)))
