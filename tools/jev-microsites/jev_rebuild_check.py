#!/usr/bin/env python3
"""Checks of a rebuilt homepage (``jev_rebuild_lib.rebuild_archs`` output).

:func:`validate_rebuilt` returns a list of error messages (empty when the
archs may be proposed): every language key present and well-formed XML (lxml),
the section order equal to the standard skeleton minus the omitted sections,
no company text of the reference site leaking in, the image URLs pointing at
the right company, the collapse ids using the right slug, the carried-over
texts reading back equal to the current arch of the same language, and the
translation terms of every language lining up with the primary language
(``jev_rebuild_terms.translation_mapping``).
"""
from __future__ import annotations

import re

from lxml import etree

import jev_apply_lib as lib
import jev_rebuild_lib as rb
import jev_rebuild_terms as terms

_COMPANY_ID_RE = re.compile(r"/web/image/res\.company/(\d+)/(microsite_\w+)")
_COLLAPSE_SLUG_RE = re.compile(r'acerca\d+_([A-Za-z0-9_-]+)"')

# Standard section -> company image field expected in its background.
SECTION_IMAGES = {"Hero": "microsite_hero_image", "SEC1": "microsite_intro_image",
                  lib.STRIP_SECTION: "microsite_banner_image"}


def well_formed(arch: str) -> str:
    """``""`` when ``arch`` parses as XML, else the parser message."""
    try:
        etree.fromstring(arch)
    except etree.XMLSyntaxError as exc:
        return str(exc)
    return ""


def expected_order(omitted: list[str]) -> list[str]:
    return [name for name in rb.STANDARD_ORDER if name not in omitted]


def reference_private_texts(reference: str) -> list[str]:
    """Texts of the reference arch that belong to the reference company
    (headline, SEC1, Acerca excerpts and full texts); the platform strip
    title and the column titles are shared vocabulary and are not listed."""
    texts = rb.extract_site_texts(reference)
    private = [texts.h1, texts.sec1]
    for column in texts.columns.values():
        private += [column.excerpt, column.text]
    return [lib.normalize_text(t) for t in private if t and lib.normalize_text(t)]


def _leaks(arch: str, reference: str, lang: str) -> list[str]:
    errors = []
    plain = lib.normalize_text(arch)
    for text in reference_private_texts(reference):
        if text in plain:
            errors.append(f"{lang}: reference text leaked: {lib.truncate(text, 60)!r}")
    ref_texts = rb.extract_site_texts(reference)
    if ref_texts.slug and re.search(rf"acerca\d+_{re.escape(ref_texts.slug)}\b", arch):
        errors.append(f"{lang}: reference slug {ref_texts.slug!r} leaked into a collapse id")
    return errors


def _images(arch: str, company_id: int, omitted: list[str], lang: str) -> list[str]:
    errors = []
    found = {(int(cid), field) for cid, field in _COMPANY_ID_RE.findall(arch)}
    wrong = sorted(cid for cid, _ in found if cid != int(company_id))
    if wrong:
        errors.append(f"{lang}: image URLs point at company ids {wrong}, expected {company_id}")
    expected = {image for section, image in SECTION_IMAGES.items() if section not in omitted}
    fields = {field for _, field in found}
    if fields != expected:
        errors.append(f"{lang}: image fields {sorted(fields)} differ from expected {sorted(expected)}")
    return errors


def _collapse_ids(arch: str, slug: str, omitted: list[str], lang: str) -> list[str]:
    slugs = set(_COLLAPSE_SLUG_RE.findall(arch))
    if "Acerca" in omitted:
        return [f"{lang}: collapse ids present although Acerca is omitted"] if slugs else []
    if slugs != {slug}:
        return [f"{lang}: collapse ids use slugs {sorted(slugs)}, expected {slug!r}"]
    return []


def _preserved(after: str, before: str, lang: str, omitted: list[str]) -> list[str]:
    """The texts carried over read back equal to the site's current arch."""
    new, old = rb.extract_site_texts(after).preserved(), rb.extract_site_texts(before).preserved()
    errors = []
    if old["h1"] and new["h1"] != old["h1"]:
        errors.append(f"{lang}: headline changed: {old['h1']!r} -> {new['h1']!r}")
    if "SEC1" not in omitted and new["sec1"] != old["sec1"] and old["sec1"]:
        errors.append(f"{lang}: SEC1 text changed")
    if old["separador"] and new["separador"] != old["separador"]:
        errors.append(f"{lang}: Separador text changed")
    if "Acerca" not in omitted:
        for n, column in old["columns"].items():
            if new["columns"].get(n) != column:
                errors.append(f"{lang}: Acerca column {n} texts changed")
    return errors


def validate_rebuilt(after: dict[str, str], before: dict[str, str], reference: dict[str, str],
                     company_id: int, slug: str, omitted: list[str],
                     primary: str = lib.DEFAULT_PRIMARY_LANG) -> list[str]:
    """Every problem found in the rebuilt archs (empty list = fine)."""
    errors: list[str] = []
    for name, keys in (("site", set(before)), ("rebuilt", set(after))):
        if keys != set(reference):
            errors.append(f"{name} language keys {sorted(keys)} differ from the reference {sorted(reference)}")
    if errors:
        return errors
    order = expected_order(omitted)
    for lang, arch in after.items():
        problem = well_formed(arch)
        if problem:
            errors.append(f"{lang}: not well-formed XML: {problem}")
            continue
        names = rb.section_names(arch)
        if names != order:
            errors.append(f"{lang}: section order {'>'.join(names)} differs from {'>'.join(order)}")
        errors += _leaks(arch, reference[lang], lang)
        errors += _images(arch, company_id, omitted, lang)
        errors += _collapse_ids(arch, slug, omitted, lang)
        errors += _preserved(arch, before[lang], lang, omitted)
        if "facilities_block" not in arch or "certification_block" not in arch:
            errors.append(f"{lang}: facilities/certification calls missing")
    if errors:
        return errors
    try:
        terms.translation_mapping(after, primary)
    except terms.TermError as exc:
        errors.append(f"translation terms do not line up: {exc}")
    return errors
