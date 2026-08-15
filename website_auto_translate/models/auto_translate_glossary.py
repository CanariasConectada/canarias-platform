# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from markupsafe import escape

from odoo import api, fields, models, tools

# The only thing this engine reliably leaves alone. Measured against our own
# LibreTranslate on 2026-08-15 with "Camiseta X de algodon" (es -> de):
#
#   ‹0›, {0}, @@0@@   vanished from the output entirely
#   __0__             came back as "     0      "
#   %%0%%             came back as "%% 0%"
#   [[0]], #0#        came back as "[0]" and "# 0 #"
#   <x0/>             came back as "< x0 / >"
#   <span translate="no">Cheetos</span>   came back verbatim
#
# The first group is the dangerous one: a placeholder that disappears takes the
# brand with it and nobody notices until a customer does. So the guard is the
# web standard rather than a token of our own invention, and every request goes
# out as HTML because that is the only format in which the span is honoured.
PROTECTED = '<span translate="no">%s</span>'

# Deliberately tolerant coming back: the engine is entitled to reformat the
# attribute, and a guard we cannot find again is a guard that deletes text.
RESTORE = re.compile(
    r"""<span[^>]*\btranslate\s*=\s*["']?\s*no\s*["']?[^>]*>(.*?)</span>""",
    re.IGNORECASE | re.DOTALL,
)

# Entities are protected for the same reason as brands, not as a nicety. Both
# formats damage them: `text` turned "&nbsp;" into the literal "& nbsp;" -- the
# corruption found in eight footers on 2026-08-15 -- and `html` swallowed it
# along with the words either side of it.
ENTITY = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]{1,31});")

# Splits markup from content while keeping both, so a term is never matched
# inside an attribute: translating the "Milka" in `alt="Milka"` would rewrite
# the markup rather than the sentence.
MARKUP = re.compile(r"(<[^>]*>)")


class AutoTranslateGlossary(models.Model):
    """A word the machine is not allowed to translate.

    Brand and place names are the ones that hurt: our LibreTranslate turned
    "Cheetos" into "Käse" and "Estrella Galicia mini" into "Ministern Galicia",
    which is not a bad translation but a wrong product. There is no setting for
    this, so the term has to be held back from the request altogether.
    """

    _name = "auto.translate.glossary"
    _description = "Protected Term"
    _order = "name"

    name = fields.Char(
        string="Term",
        required=True,
        help="Exactly as it is written in the source text. Matched whole-word "
        "and case-insensitively, so 'Milka' also protects 'MILKA'.",
    )
    replacement = fields.Char(
        string="Always translate as",
        help="Leave empty to keep the term untouched, which is what a brand "
        "name normally wants. Fill it in only when the term does have an "
        "official wording in the target language.",
    )
    lang = fields.Char(
        string="Only for language",
        help="Language code the replacement applies to, e.g. de_DE. Leave "
        "empty for every language.",
    )
    active = fields.Boolean(default=True)
    note = fields.Char(string="Why", help="For whoever reads this in a year.")

    _term_per_lang = models.Constraint(
        "UNIQUE (name, lang)",
        "That term already has a rule for that language.",
    )

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------
    @api.model
    @tools.ormcache()
    def _index(self):
        """Every rule, longest term first.

        Longest first is not tidiness. With both "Estrella Galicia" and
        "Galicia" in the glossary, matching the short one first would leave
        "Estrella" outside the guard and the engine would translate half a
        brand -- which is worse than translating all of it, because it still
        looks deliberate.
        """
        rules = {}
        for entry in self.sudo().search([]):
            rules.setdefault(entry.name, {})[entry.lang or ""] = entry.replacement or ""
        return tuple(
            (term, tuple(sorted(by_lang.items())))
            for term, by_lang in sorted(rules.items(), key=lambda kv: -len(kv[0]))
        )

    @api.model
    @tools.ormcache()
    def _pattern(self):
        """One alternation for terms and entities together.

        A single pass matters: protecting terms and entities in two passes
        would let the second one match inside the ``<span>`` the first one just
        inserted, and nest guards until the restore no longer pairs up.
        """
        parts = []
        for term, _rules in self._index():
            escaped = re.escape(term)
            # Only fence a term that starts or ends on a word character.
            # "S.L." and "&" would never match with \b around them.
            if term[:1].isalnum():
                escaped = r"(?<!\w)" + escaped
            if term[-1:].isalnum():
                escaped = escaped + r"(?!\w)"
            parts.append(escaped)
        parts.append(ENTITY.pattern)
        return re.compile("|".join(parts), re.IGNORECASE)

    def _clear(self):
        self.env.registry.clear_cache()

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        self._clear()
        return records

    def write(self, vals):
        result = super().write(vals)
        self._clear()
        return result

    def unlink(self):
        result = super().unlink()
        self._clear()
        return result

    # ------------------------------------------------------------------
    # Protecting and restoring
    # ------------------------------------------------------------------
    @api.model
    def _protect(self, text, is_html):
        """Wrap everything the engine must leave alone.

        Plain text is escaped on the way in because the request goes out as
        HTML either way -- that is the only format in which the guard is
        honoured -- and an unescaped ``&`` in a product name would otherwise be
        read as the start of markup.
        """
        if not text:
            return text
        if not is_html:
            text = str(escape(text))
        pattern = self._pattern()
        pieces = []
        for index, piece in enumerate(MARKUP.split(text)):
            # Odd indices are the tags themselves: never touch them.
            if index % 2 == 0 and piece:
                piece = pattern.sub(lambda match: PROTECTED % match.group(0), piece)
            pieces.append(piece)
        return "".join(pieces)

    @api.model
    def _restore(self, text, target_lang, is_html):
        """Put the guarded terms back, in their final form."""
        if not text:
            return text
        replacements = {
            term: dict(rules) for term, rules in self._index()
        }

        def put_back(match):
            held = match.group(1)
            rules = replacements.get(held) or {}
            # An exact-language rule wins over the catch-all; with neither, the
            # term stays exactly as it was written, which is the whole point.
            return rules.get(target_lang) or rules.get("") or held

        text = RESTORE.sub(put_back, text)
        if not is_html:
            # Deliberately not ``html2plaintext``: it collapses whitespace and
            # adds newlines, which would quietly reshape every product name it
            # touched. A stray tag is stripped and nothing else moves.
            text = MARKUP.sub("", text)
            text = _unescape(text)
        return text


def _unescape(text):
    """Undo the escaping :meth:`_protect` applied to plain text.

    ``&amp;`` goes last: doing it first would turn ``&amp;lt;`` -- a product
    name that genuinely contains the text "&lt;" -- into a tag on the way back.
    """
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&amp;", "&")
    )
