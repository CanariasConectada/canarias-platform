#!/usr/bin/env python3
"""Rebuild a deviating homepage arch onto the standard section skeleton.

The standard homepage (reference: view 3218, ``website.homepage_flashprint``)
is ``Hero > Horario > SEC1 > Acerca > Separador > Formulario > Subvenciones``
plus the ``facilities_block`` / ``certification_block`` calls between the
strip and the form. Everything in it is template except: the company id in the
three ``/web/image/res.company/<id>/microsite_*_image`` URLs, the slug of the
``acerca<N>_<slug>`` collapse ids, the root ``<t name= t-name=>`` tag, the Hero
``<h1>`` text, the SEC1 ``<h2>``, the two Acerca columns (``<h6>`` title,
``<small>`` excerpt, ``card-body`` full text) and the Separador ``<h2>``.

:func:`rebuild_archs` takes the reference arch and the site's current arch of
EVERY language key and renders the site's homepage, language by language, from
the reference arch of the SAME language: template texts (Horario labels, form
labels, "Leer más", ...) come from the reference's translation, the site's own
texts are carried over from the site's arch of that language. Nothing is ever
invented: a site without SEC1 or Acerca text gets that section omitted and a
flag. :func:`validate_rebuilt` checks the result (:mod:`jev_rebuild_check`).

Regex based like ``jev_apply_lib``; the reference arch stays byte-identical
outside the replaced spans.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

import jev_apply_lib as lib

STANDARD_ORDER = ("Hero", "Horario", "SEC1", "Acerca", "Separador", "Formulario", "Subvenciones")
OPTIONAL_SECTIONS = ("SEC1", "Acerca")
# Single remaining Acerca column: centred like the legacy one-column pages.
TWO_COLUMN_CLASS = "col-lg-6"
ONE_COLUMN_CLASS = "col-lg-8 offset-lg-2"

_SECTION_NAME_RE = re.compile(r'<section\b[^>]*\sdata-name="([^"]+)"')
_ROOT_TAG_RE = re.compile(r"\A\s*<t\b[^>]*>")
_T_NAME_SLUG_RE = re.compile(r'\st-name="website\.homepage_([A-Za-z0-9_-]+)"')
_COMPANY_URL_RE = re.compile(r"/web/image/res\.company/(\d+)/microsite_")
_ACERCA_ID_RE = re.compile(r'(acerca\d+_)([A-Za-z0-9_-]+)(?=")')
_GRADIENT_RE = re.compile(r"linear-gradient")
_EMAIL_RE = re.compile(r">[^<]*[\w.+-]+@[\w-]+\.[\w.-]+[^<]*<")


class RebuildError(lib.ArchError):
    """The arch cannot be rebuilt (missing cover headline, bad reference...)."""


@dataclass
class ColumnTexts:
    title: str
    excerpt: str
    text: str


@dataclass
class SiteTexts:
    """Per-company texts of one language of a homepage arch."""

    h1: str | None = None
    sec1: str | None = None
    separador: str | None = None
    columns: dict[int, ColumnTexts] = field(default_factory=dict)
    slug: str | None = None
    root_tag: str | None = None

    def preserved(self) -> dict:
        """Comparable form (whitespace-normalized) of the texts kept."""
        return {
            "h1": lib.normalize_text(self.h1), "sec1": lib.normalize_text(self.sec1),
            "separador": lib.normalize_text(self.separador),
            "columns": {n: (lib.normalize_text(c.title), lib.normalize_text(c.excerpt), lib.normalize_text(c.text))
                        for n, c in sorted(self.columns.items())},
        }


def section_names(arch: str) -> list[str]:
    """``data-name`` of every ``<section>`` in document order (nested ones
    included, ``Column`` divs are not sections)."""
    return _SECTION_NAME_RE.findall(arch)


def section_list(arch: str) -> str:
    """``Hero>SEC1>...`` form of :func:`section_names` (the ``valor_anterior``
    of a rebuild row)."""
    return ">".join(section_names(arch))


def extract_site_texts(arch: str) -> SiteTexts:
    """Read the per-company texts of one language of a homepage arch."""
    texts = SiteTexts()
    root = _ROOT_TAG_RE.match(arch)
    texts.root_tag = root.group(0).strip() if root else None
    hero = lib._hero_section(arch)
    texts.h1 = lib.extract_section_h1(arch, hero.name) if hero else None
    for attr, name in (("sec1", "SEC1"), ("separador", lib.STRIP_SECTION)):
        if lib.find_section(arch, name):
            setattr(texts, attr, lib.extract_section_h2(arch, name))
    if lib.find_section(arch, lib.ACERCA_SECTION):
        for n, column in lib.acerca_column_slots(arch).items():
            text = lib.extract_acerca_column(arch, n)
            if not text.strip():
                continue
            small = lib._inner_span(arch, column, lib._SMALL_OPEN_RE, lib._SMALL_CLOSE_RE)
            excerpt = lib._plain(arch[small[0]:small[1]]) if small else lib.acerca_preview(text)
            texts.columns[n] = ColumnTexts(lib.extract_acerca_heading(arch, n) or "", excerpt, text)
    m = lib._ACERCA_SLUG_IN_ARCH_RE.search(arch) or _T_NAME_SLUG_RE.search(arch)
    texts.slug = m.group(1) if m else None
    return texts


def reference_company_id(reference: str) -> int:
    """Company id of the reference arch's image URLs (exactly one expected)."""
    ids = set(_COMPANY_URL_RE.findall(reference))
    if len(ids) != 1:
        raise RebuildError(f"reference arch must reference exactly one company id in its image URLs, got {sorted(ids)}")
    return int(ids.pop())


def _remove_span(arch: str, start: int, end: int) -> str:
    """Drop ``arch[start:end]`` together with its line prefix and the newline
    that follows, so the surrounding lines close up."""
    line_start = arch.rfind("\n", 0, start) + 1
    if arch[line_start:start].strip():
        line_start = start
    if arch[end:end + 1] == "\n":
        end += 1
    return arch[:line_start] + arch[end:]


def _remove_section(arch: str, name: str) -> str:
    section = lib.find_section(arch, name)
    if section is None:
        raise RebuildError(f"reference arch has no {name!r} section")
    return _remove_span(arch, section.start, section.end)


def _set_column_texts(arch: str, column: lib.Column, texts: ColumnTexts) -> str:
    h6 = lib._inner_span(arch, column, lib._H6_OPEN_RE, lib._H6_CLOSE_RE)
    small = lib._inner_span(arch, column, lib._SMALL_OPEN_RE, lib._SMALL_CLOSE_RE)
    card = lib._card_body_span(arch, column)
    if not (h6 and small and card):
        raise RebuildError("reference Acerca column lacks <h6>, <small> or card-body")
    edits = sorted([(h6, texts.title), (small, texts.excerpt), (card, texts.text)], reverse=True)
    for (start, end), value in edits:
        arch = arch[:start] + html.escape(value, quote=False) + arch[end:]
    return arch


def _render_acerca(arch: str, columns: dict[int, ColumnTexts]) -> str:
    if not columns:
        return _remove_section(arch, lib.ACERCA_SECTION)
    slots = lib.acerca_column_slots(arch)
    if set(slots) != {1, 2}:
        raise RebuildError(f"reference Acerca must have columns 1 and 2, got {sorted(slots)}")
    for n in (2, 1):   # right to left so earlier offsets stay valid
        column = slots[n]
        if n in columns:
            arch = _set_column_texts(arch, column, columns[n])
        else:
            arch = arch[:column.start] + arch[column.end:]
    if len(columns) == 1:
        column = lib.acerca_column_slots(arch)[next(iter(columns))]
        open_tag = arch[column.start:column.open_end]
        arch = arch[:column.start] + open_tag.replace(TWO_COLUMN_CLASS, ONE_COLUMN_CLASS, 1) + arch[column.open_end:]
    return arch


def render_arch(reference: str, texts: SiteTexts, company_id: int, slug: str) -> str:
    """One language: the reference arch of that language with the site's
    company id, slug, root tag and texts. SEC1/Acerca are omitted when
    ``texts`` has no text for them; a missing Separador text keeps the
    reference's (platform) title. Raises :class:`RebuildError` when the
    cover headline is missing."""
    if not (texts.h1 or "").strip():
        raise RebuildError("no cover headline (Hero/Portada <h1>) to carry over")
    ref_root = _ROOT_TAG_RE.match(reference)
    if not ref_root or not texts.root_tag:
        raise RebuildError("reference or site arch has no root <t> tag")
    arch = texts.root_tag + reference[ref_root.end():]
    arch = _COMPANY_URL_RE.sub(f"/web/image/res.company/{int(company_id)}/microsite_", arch)
    arch = _ACERCA_ID_RE.sub(lambda m: m.group(1) + slug, arch)
    arch = lib.replace_section_h1(arch, "Hero", texts.h1)
    arch = lib.replace_section_h2(arch, "SEC1", texts.sec1) if texts.sec1 else _remove_section(arch, "SEC1")
    arch = _render_acerca(arch, texts.columns)
    if texts.separador:
        arch = lib.replace_section_h2(arch, lib.STRIP_SECTION, texts.separador)
    return arch


def rebuild_archs(reference: dict[str, str], before: dict[str, str], company_id: int,
                  slug: str | None = None) -> tuple[dict[str, str], list[str], list[str]]:
    """Rebuild every language key. Returns ``(archs, omitted, flags)``:
    ``omitted`` are the standard sections left out (decided on the primary
    language, applied to all), ``flags`` the human-readable notes of what was
    dropped or could not be carried over. Raises :class:`RebuildError`."""
    missing = sorted(set(before) ^ set(reference))
    if missing:
        raise RebuildError(f"language keys differ between site and reference: {missing}")
    primary = lib.DEFAULT_PRIMARY_LANG if lib.DEFAULT_PRIMARY_LANG in before else sorted(before)[0]
    texts = {lang: extract_site_texts(arch) for lang, arch in before.items()}
    main = texts[primary]
    slug = slug or main.slug
    if not slug or not lib.ACERCA_SLUG_RE.match(slug):
        raise RebuildError(f"cannot determine the site slug ({slug!r})")
    omitted, flags = [], []
    if not main.sec1:
        omitted.append("SEC1")
        flags.append("SEC1 omitted: the page has no SEC1 heading (client must supply the intro text)")
    if not main.columns:
        omitted.append("Acerca")
        flags.append("Acerca omitted: the page has no Acerca column text (client must supply the about/services texts)")
    elif len(main.columns) == 1:
        flags.append(f"Acerca keeps its single column {next(iter(main.columns))} (centred); the other column is not invented")
    if not main.separador:
        flags.append("Separador added with the platform title of the reference (page had no strip)")
    for name in section_names(before[primary]):
        if name not in STANDARD_ORDER:
            flags.append(f"section {name!r} dropped (legacy layout)")
    for name in ("Hero", "Portada", lib.STRIP_SECTION):
        section = lib.find_section(before[primary], name)
        if section and _GRADIENT_RE.search(section.open_tag):
            flags.append(f"{name} used a gradient instead of the company image; standard image URL applied")
    if any(section and _EMAIL_RE.search(section.body) for section in
           (lib.find_section(before[primary], name) for name in ("Formulario", "Formulario Contacto"))):
        flags.append("hardcoded contact text in the old form block dropped (standard live blocks used)")
    if main.root_tag and f'name="Home - {slug}"' not in main.root_tag:
        flags.append(f"root tag kept verbatim although its name is unusual: {main.root_tag}")
    archs = {}
    for lang, arch in reference.items():
        lang_texts = texts[lang]
        lang_texts.root_tag = main.root_tag
        _align_with_primary(lang, lang_texts, main, omitted, flags)
        archs[lang] = render_arch(arch, lang_texts, company_id, slug)
    return archs, omitted, flags


def _align_with_primary(lang: str, texts: SiteTexts, main: SiteTexts, omitted: list[str], flags: list[str]) -> None:
    """Give ``texts`` the structure decided on the primary language: omitted
    sections go, and a text the language lacks falls back to the primary one
    (flagged) so every language renders the same skeleton."""
    if "SEC1" in omitted:
        texts.sec1 = None
    for attr in ("h1", "sec1", "separador"):
        if getattr(main, attr) and not (getattr(texts, attr) or "").strip():
            flags.append(f"{lang}: no {attr} text in that language, primary one used")
            setattr(texts, attr, getattr(main, attr))
    columns = {}
    for n, column in main.columns.items():
        if n not in texts.columns:
            flags.append(f"{lang}: Acerca column {n} missing in that language, primary one used")
        columns[n] = texts.columns.get(n, column)
    texts.columns = {} if "Acerca" in omitted else columns
