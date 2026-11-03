# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import re

from markupsafe import escape

from odoo import api, fields, models, tools

from .text_tools import ENTITY as _ENTITY

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
#
# The doubly-escaped form comes first and that ordering is load-bearing. Odoo's
# website builder stores a typed non-breaking space as the text "&amp;nbsp;",
# and an alternation that tried the plain form first would match the leading
# "&amp;" -- a perfectly valid entity on its own -- fence off that much, and
# leave a bare "nbsp;" outside the guard as ordinary translatable words. Which
# is exactly what the Italian model then capitalised into "&Nbsp;": not an
# entity at all, five characters the visitor reads. Eight views on production,
# 2026-08-16. The expression itself lives in :mod:`text_tools`, which needs it
# for the same reason when it changes the case of a heading.
ENTITY = _ENTITY

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
    @tools.ormcache("lang")
    def _index(self, lang=None):
        """Every rule that applies to ``lang``, longest term first.

        Longest first is not tidiness. With both "Estrella Galicia" and
        "Galicia" in the glossary, matching the short one first would leave
        "Estrella" outside the guard and the engine would translate half a
        brand -- which is worse than translating all of it, because it still
        looks deliberate.

        Passing ``lang`` drops the rules written for a *different* language,
        and that is the difference between a guard and a gag. "cookies" was
        added for German and Italian, where the engine was turning it into
        biscuits; with no language filter it was fenced off in French too, and
        the engine handed back "Las cookies sont de petits fichiers" -- unable
        to resolve the article once the noun had been walled off. A term
        scoped to another language is ordinary words here, and has to be
        translatable as such.

        ``lang=None`` still means "every rule", which is what :meth:`_restore`
        wants: it needs to recognise anything that may come back.
        """
        rules = {}
        for entry in self.sudo().search([]):
            scope = entry.lang or ""
            if lang is not None and scope and scope != lang:
                continue
            rules.setdefault(entry.name, {})[scope] = entry.replacement or ""
        return tuple(
            (term, tuple(sorted(by_lang.items())))
            for term, by_lang in sorted(rules.items(), key=lambda kv: -len(kv[0]))
        )

    @api.model
    @tools.ormcache("lang")
    def _pattern(self, lang=None):
        """One alternation for terms and entities together.

        A single pass matters: protecting terms and entities in two passes
        would let the second one match inside the ``<span>`` the first one just
        inserted, and nest guards until the restore no longer pairs up.

        Cached per language because the term list is per language; entities are
        in every one of them.
        """
        parts = []
        for term, _rules in self._index(lang):
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
    # Repairing what was translated before the term existed
    # ------------------------------------------------------------------
    def action_retranslate_affected(self):
        """Queue everything whose source mentions these terms.

        Adding a term only guards translations made *after* it, which is no use
        at all when the reason for adding it is a brand that is already wrong in
        1424 products. This finds the content that mentions the term and hands
        it back to the queue.

        Corrections made by hand are left alone: :meth:`action_translate_again`
        skips a locked row, so somebody who already fixed a product keeps their
        wording.
        """
        Job = self.env["auto.translate.job"].sudo()
        source_lang = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param("website_auto_translate.source_lang", "es_ES")
        )
        queued = 0
        for model_name in sorted(self.env.registry):
            model = self.env[model_name]
            if model._abstract or model._transient:
                continue
            if not hasattr(model, "_auto_translate_fields"):
                continue
            for field_name in model._auto_translate_fields():
                field = model._fields.get(field_name)
                if field is None or not field.translate or not field.store:
                    continue
                domain = ["|"] * (len(self) - 1) + [
                    (field_name, "ilike", entry.name) for entry in self
                ]
                # Searched in the source language on purpose: a term that only
                # appears in the machine's German output is the machine's
                # invention, not content anybody wrote.
                hits = (
                    model.sudo()
                    .with_context(lang=source_lang, active_test=False)
                    .search(domain)
                )
                if not hits:
                    continue
                queued += Job.search(
                    [
                        ("model_name", "=", model_name),
                        ("field_name", "=", field_name),
                        ("res_id", "in", hits.ids),
                    ]
                ).action_translate_again()
        return queued

    # ------------------------------------------------------------------
    # Protecting and restoring
    # ------------------------------------------------------------------
    @api.model
    def _protect(self, text, is_html, held=None, target_lang=None):
        """Wrap everything the engine must leave alone, for one language.

        ``target_lang`` is what keeps a rule written for German from silencing
        the same word in French. Leaving it out fences every rule in the
        glossary, which is only right when there is no target to speak of.

        ``held`` is filled with what was fenced off, keyed case-insensitively,
        so :meth:`_restore` can put back the exact bytes that went out instead
        of trusting what comes back. That is not paranoia: the Italian model
        returned ``&Nbsp;`` for a guarded ``&nbsp;`` on 2026-08-15, and an HTML
        entity is case-sensitive -- ``&Nbsp;`` is not an entity at all, it is
        five visible characters on the page.

        Plain text is escaped on the way in because the request goes out as
        HTML either way -- that is the only format in which the guard is
        honoured -- and an unescaped ``&`` in a product name would otherwise be
        read as the start of markup.
        """
        if not text:
            return text
        if not is_html:
            text = str(escape(text))
        pattern = self._pattern(target_lang)

        def fence(match):
            found = match.group(0)
            if held is not None:
                held[found.casefold()] = found
            return PROTECTED % found

        pieces = []
        for index, piece in enumerate(MARKUP.split(text)):
            # Odd indices are the tags themselves: never touch them.
            if index % 2 == 0 and piece:
                piece = pattern.sub(fence, piece)
            pieces.append(piece)
        return "".join(pieces)

    @api.model
    def _restore(self, text, target_lang, is_html, held=None):
        """Put the guarded terms back, in their final form."""
        if not text:
            return text
        replacements = {term.casefold(): dict(rules) for term, rules in self._index()}

        def put_back(match):
            returned = match.group(1)
            # What we sent wins over what came back, whenever we still know it.
            original = (held or {}).get(returned.casefold(), returned)
            rules = replacements.get(original.casefold()) or {}
            # An exact-language rule wins over the catch-all; with neither, the
            # term stays exactly as it was written, which is the whole point.
            wording = rules.get(target_lang) or rules.get("")
            if not wording:
                return original
            # ``held`` is shared by every sentence of a request and keyed
            # case-insensitively, so the last "comercios" fenced in the prose
            # overwrites the "Comercios" of the button that went out earlier.
            # For the *case* of a replacement, what came back is the better
            # witness: the engine returns a guarded term byte for byte.
            shape = returned if returned.casefold() == original.casefold() else original
            return _follow_case(shape, wording)

        text = RESTORE.sub(put_back, text)
        if not is_html:
            # Deliberately not ``html2plaintext``: it collapses whitespace and
            # adds newlines, which would quietly reshape every product name it
            # touched. A stray tag is stripped and nothing else moves.
            text = MARKUP.sub("", text)
            text = _unescape(text)
        return text


def _follow_case(original, wording):
    """Shape a glossary replacement like the term it replaces.

    A rule is written once, in the form that suits running prose
    ("comercios" -> "shops"). The same word opens a button or a heading with
    a capital, and came back as "shops" there on 2026-08-26: the rule was
    pasted verbatim. Title case in, title case out; capitals in, capitals
    out; anything else is left as the rule was written.
    """
    if original.isupper() and len(original) > 1:
        return wording.upper()
    if original[:1].isupper() and wording[:1].islower():
        return wording[:1].upper() + wording[1:]
    return wording


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
