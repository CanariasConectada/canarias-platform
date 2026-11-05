"""Simulation of how Odoo 19 stores a terms-translated field (``arch_db``).

Ports, from ``odoo/orm/fields_textual.py`` (``Text.write``,
``get_translation_dictionary``) and ``odoo/orm/models.py``
(``_update_field_translations``):

* :func:`write`: a write in language ``lang`` rebuilds every other language
  term by term: positional dictionary from the old ``lang`` value to each
  old translation (identity when the term counts differ), old terms absent
  from the new value remapped onto the new term with the same text content
  (``difflib.get_close_matches`` cutoff 0.9), unknown terms left as written.
* :func:`update_field_translations`: each given language is rebuilt from
  the ``source_lang`` value through ``{**positional_old, **given}``;
  languages with an empty mapping are dropped.

``translate(callback, value)`` is pluggable: :func:`real_xml_translate`
returns Odoo's own when the source tree is importable (the real-file test),
the fixture tests use the string-level ``rebuild_fixtures.translate_arch``.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from difflib import get_close_matches
from pathlib import Path

from lxml import html

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jev_rebuild_terms as terms  # noqa: E402


def get_text_content(term: str) -> str:
    """``xml_translate.get_text_content``: text of the term, whitespace collapsed."""
    return " ".join(html.fromstring(f"<div>{term}</div>").text_content().split())


def real_xml_translate(odoo_src: Path = terms.DEFAULT_ODOO_SRC):
    """Odoo's ``xml_translate`` or ``None`` when not importable."""
    if terms.oracle_terms("<div>x</div>", odoo_src) is None:
        return None
    from odoo.tools.translate import xml_translate  # type: ignore
    return xml_translate


def translation_dictionary(from_value: str, to_values: dict[str, str]) -> dict:
    """``{from_term: {lang: to_term}}`` by position; identity when counts differ."""
    from_terms = terms.extract_terms(from_value)
    dictionary = {term: defaultdict(dict) for term in from_terms}
    for lang, to_value in to_values.items():
        to_terms = terms.extract_terms(to_value)
        for index, term in enumerate(from_terms):
            dictionary[term][lang] = to_terms[index] if len(to_terms) == len(from_terms) else term
    return dictionary


def write(stored: dict[str, str], new_value: str, lang: str, translate) -> dict[str, str]:
    """Stored ``{lang: value}`` after ``record.with_context(lang=lang).write({field: new_value})``."""
    old = dict(stored)
    from_value = old.pop(lang, old["en_US"])
    dictionary = translation_dictionary(from_value, old)
    new_terms = set(terms.extract_terms(new_value))
    text2terms: dict[str, list[str]] = defaultdict(list)
    for term in new_terms:
        if text := get_text_content(term):
            text2terms[text].append(term)
    for old_term in list(dictionary):
        if old_term in new_terms:
            continue
        matches = get_close_matches(get_text_content(old_term), text2terms, 1, 0.9)
        if not matches:
            continue
        closest = get_close_matches(old_term, text2terms[matches[0]], 1, 0)[0]
        if closest not in dictionary:
            dictionary[closest] = dictionary.pop(old_term)
    result = {other: translate(lambda term, o=other: dictionary.get(term, {o: None})[o], new_value) for other in old}
    result[lang] = new_value
    return result


def update_field_translations(stored: dict[str, str], translations: dict[str, dict[str, str]],
                              source_lang: str, translate) -> dict[str, str]:
    """Stored ``{lang: value}`` after ``record.update_field_translations(field, translations, source_lang)``."""
    values = dict(stored)
    source_value = values[source_lang]
    translations = {lang: pairs for lang, pairs in translations.items() if pairs}
    to_values = {lang: value for lang, value in values.items() if lang != source_lang and lang in translations}
    dictionary = translation_dictionary(source_value, to_values)
    for lang, pairs in translations.items():
        old = {source: targets[lang] for source, targets in dictionary.items() if lang in targets}
        mapping = {**old, **pairs}
        values[lang] = translate(mapping.get, source_value)
    return values


def apply_rebuild(stored: dict[str, str], proposal: dict[str, str], translate,
                  primary: str = "es_ES") -> dict[str, str]:
    """The two RPCs of a ``Homepage.rebuild`` row, simulated."""
    after_write = write(stored, proposal[primary], primary, translate)
    return update_field_translations(after_write, terms.translation_mapping(proposal, primary), primary, translate)
