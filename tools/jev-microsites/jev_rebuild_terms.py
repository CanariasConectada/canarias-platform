#!/usr/bin/env python3
"""Translation terms of a view arch, the way Odoo's ``xml_translate`` sees them.

``ir.ui.view.arch_db`` is a jsonb ``{lang: arch}`` whose languages Odoo keeps
in sync *term by term*: ``update_field_translations(field, {lang: {source_term:
term}}, source_lang=...)`` rebuilds a language from the source language arch,
replacing each source term through the given mapping. The keys of that mapping
must therefore be the exact term strings Odoo extracts from the source arch.

:func:`extract_terms` is a port of the term walk of
``odoo.tools.translate.translate_xml_node`` (Odoo 19), restricted to term
collection (nothing is rewritten). :func:`oracle_terms` runs the real Odoo
function when the source tree is importable so a dry run can prove both
agree on every generated arch. :func:`translation_mapping` pairs the terms of
every language with the primary language by position, which is only valid for
archs rendered from the same skeleton (see ``jev_rebuild_lib``).

Only lxml and the standard library are needed.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from lxml import etree

DEFAULT_ODOO_SRC = Path(os.environ.get("ODOO_SRC", "/home/odoo/odoo"))

# Mirrors odoo/tools/translate.py (19.0).
TRANSLATED_ELEMENTS = {
    "abbr", "b", "bdi", "bdo", "br", "cite", "code", "data", "del", "dfn", "em",
    "font", "i", "ins", "kbd", "keygen", "mark", "math", "meter", "output",
    "progress", "q", "ruby", "s", "samp", "small", "span", "strong", "sub",
    "sup", "time", "u", "var", "wbr", "text", "select", "option",
}
TRANSLATED_ATTRS = {
    "string", "add-label", "help", "sum", "avg", "confirm", "placeholder", "alt", "title", "aria-label",
    "aria-keyshortcuts", "aria-placeholder", "aria-roledescription", "aria-valuetext",
    "value_label", "data-tooltip", "label", "confirm-label", "confirm-title", "cancel-label",
}
TRANSLATED_ATTRS |= {f"t-attf-{attr}" for attr in TRANSLATED_ATTRS}
SKIPPED_ELEMENTS = ("script", "style", "title")
_SPACE_RE = re.compile(r"[\s﻿]*")
_DOCTYPE_RE = re.compile(r"\s*<!DOCTYPE", re.IGNORECASE | re.MULTILINE)
_FORMAT_RE = re.compile(r"(?:#\{(.+?)\})|(?:\{\{(.+?)\}\})")


class TermError(ValueError):
    """The arch cannot be parsed or the languages do not line up."""


def _nonspace(text) -> bool:
    return bool(text) and not _SPACE_RE.fullmatch(text)


def _is_element(node) -> bool:
    return isinstance(node.tag, str)


def _translatable_attrib(key: str, node) -> bool:
    if not key:
        return False
    if "t-call" not in node.attrib and key in TRANSLATED_ATTRS:
        return True
    return key.endswith(".translate")


def _translatable_value(node) -> bool:
    classes = node.attrib.get("class", "").split(" ")
    return (node.tag == "input" and node.attrib.get("type", "text") == "text"
            and "datetimepicker-input" not in classes) or (
        node.tag == "input" and node.attrib.get("type") == "hidden"
        and "o_translatable_input_hidden" in classes)


def _translatable_text(node) -> bool:
    return node.tag == "field" and node.attrib.get("widget", "") == "url"


def _translatable(node) -> bool:
    """Whether ``node`` is translated as part of its parent's term."""
    if not _is_element(node):
        return False
    return ("o_translate_inline" in node.attrib.get("class", "").split()
            or node.tag in TRANSLATED_ELEMENTS
            and not any(key.startswith("t-") or key.endswith(".translate") for key in node.attrib)
            and all(_translatable(child) for child in node))


def _attr_term(key: str, val: str, node) -> bool:
    return (_translatable_attrib(key, node) or (key == "value" and _translatable_value(node))
            or (key == "text" and _translatable_text(node)))


def _hastext(node, pos: int = 0) -> bool:
    if _nonspace(node[pos - 1].tail if pos else node.text):
        return True
    if pos >= len(node) or not _translatable(node[pos]):
        return False
    child = node[pos]
    return (any(val and _attr_term(key, val, child) for key, val in child.attrib.items())
            or _hastext(child) or _hastext(node, pos + 1))


def _serialize(node) -> str:
    return etree.tostring(node, method="xml", encoding="unicode")


def _mask_expressions(term: str) -> str:
    """``t-attf-*`` values: ``{{ expr }}`` / ``#{expr}`` become ``{{N}}``
    placeholders, as in Odoo's ``translate_format_string_expression``."""
    count = 0

    def placeholder(_match):
        nonlocal count
        count += 1
        return "{{%s}}" % (count - 1)
    return _FORMAT_RE.sub(placeholder, term)


def _collect(node, terms: list[str]) -> None:
    if (not _is_element(node) or node.tag in SKIPPED_ELEMENTS
            or node.get("t-translation", "").strip() == "off"
            or node.tag == "attribute" and node.get("name") not in ("value", "text")
            and not _translatable_attrib(node.get("name"), node)
            or node.getparent() is None and _DOCTYPE_RE.match(node.text or "")):
        return
    pos = 0
    while True:
        if _hastext(node, pos):
            div = etree.Element("div")
            div.text = (node[pos - 1].tail if pos else node.text) or ""
            while pos < len(node) and _translatable(node[pos]):
                div.append(node[pos])
            terms.append(_serialize(div)[5:-6].strip())
            while len(div) > 0:
                node.insert(pos, div[0])
                pos += 1
        if pos >= len(node):
            break
        _collect(node[pos], terms)
        pos += 1
    for key, val in node.attrib.items():
        if _nonspace(val) and _attr_term(key, val, node):
            terms.append(_mask_expressions(val.strip()) if key.startswith("t-") else val.strip())


def extract_terms(arch: str) -> list[str]:
    """Terms of ``arch`` in document order (port of Odoo's walk). Raises
    :class:`TermError` when the arch is not well-formed XML."""
    try:
        root = etree.fromstring(arch)
    except etree.XMLSyntaxError as exc:
        raise TermError(f"arch is not well-formed XML: {exc}") from exc
    terms: list[str] = []
    _collect(root, terms)
    return terms


def oracle_terms(arch: str, odoo_src: Path = DEFAULT_ODOO_SRC) -> list[str] | None:
    """Terms according to the real ``odoo.tools.translate.xml_translate`` of
    the Odoo source tree at ``odoo_src``; ``None`` when it cannot be imported.
    The import must not run with the Odoo directory as working directory
    (its ``http.py`` shadows the standard library there)."""
    src = str(Path(odoo_src))
    if not (Path(src) / "odoo" / "tools" / "translate.py").is_file():
        return None
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        from odoo.tools.translate import xml_translate  # type: ignore
    except Exception:  # noqa: BLE001 - any import problem means "no oracle"
        return None
    terms: list[str] = []
    xml_translate(terms.append, arch)
    return terms


def translation_mapping(archs: dict[str, str], primary: str) -> dict[str, dict[str, str]]:
    """``{lang: {primary_term: lang_term}}`` for every language but
    ``primary``, pairing terms by position. Only terms that differ are
    listed. Raises :class:`TermError` when a language has a different number
    of terms (the archs were not rendered from one skeleton) or when one
    primary term would need two different translations in a language."""
    if primary not in archs:
        raise TermError(f"primary language {primary!r} missing from the archs")
    source_terms = extract_terms(archs[primary])
    mapping: dict[str, dict[str, str]] = {}
    for lang, arch in archs.items():
        if lang == primary:
            continue
        terms = extract_terms(arch)
        if len(terms) != len(source_terms):
            raise TermError(f"{lang} has {len(terms)} terms, {primary} has {len(source_terms)}")
        pairs: dict[str, str] = {}
        for source, target in zip(source_terms, terms):
            if source == target:
                continue
            if pairs.get(source, target) != target:
                raise TermError(f"{lang}: term {source!r} maps to both {pairs[source]!r} and {target!r}")
            pairs[source] = target
        mapping[lang] = pairs
    return mapping
