# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""What an imported (static) homepage shows, read from its arch.

Pure functions, no database: the caller checks that the attachments and
company images referenced exist. Same rules as the read-only inventory of
the 2026-10 homepage review (``tools/jev-microsites/inventario_portadas.py``):

- the image slots are the ``Hero`` (or ``Portada`` / ``Cover``), ``SEC1``
  and ``Separador`` sections; an image is the ``background-image: url()``
  of the section's own ``style``, unless a later ``background:`` shorthand
  overrides it (the importer's placeholder gradient);
- the texts are the first ``<h2>`` of ``SEC1`` and ``Separador`` outside
  nested sections, and the card body of the ``Acerca`` columns 1 (about)
  and 2 (services), numbered by their ``id="acerca<N>_..."`` collapse.
"""

import re

from lxml import etree

from .legacy_homepage import safe_parser

SLOT_SECTIONS = {
    "hero": ("Hero", "Portada", "Cover"),
    "intro": ("SEC1",),
    "strip": ("Separador",),
}
ABOUT_SECTION = "Acerca"

_BG_URL_RE = re.compile(r"""background-image\s*:\s*url\(\s*(['"]?)(.*?)\1\s*\)""", re.S)
_BG_SHORTHAND_RE = re.compile(r"(?<![\w-])background\s*:\s*[^;]*;?\s*", re.S)
_ATTACHMENT_URL_RE = re.compile(
    r"^/web/(?:image|content)/(?:ir\.attachment/)?(\d+)(?:[/?_-]|$)"
)
# ``/web/image/res.company/<id>/<field>`` or ``res.partner``.
_RECORD_URL_RE = re.compile(
    r"^/web/(?:image|content)/(res\.company|res\.partner)/(\d+)/(\w+)"
)
_EXTERNAL_URL_RE = re.compile(r"^https?://", re.I)
_COLUMN_ID_RE = re.compile(r"^acerca(\d+)_")
_CARD_BODY = (
    ".//div[contains(concat(' ', normalize-space(@class), ' '), ' card ')"
    " and contains(concat(' ', normalize-space(@class), ' '), ' card-body ')]"
)


def _text(element):
    return " ".join("".join(element.itertext()).split())


def _section(tree, names):
    for name in names:
        found = tree.xpath("//section[@data-name=$name]", name=name)
        if found:
            return found[0]
    return None


def background_url(section):
    """URL of the section's effective background image, or ``None``."""
    style = section.get("style") or ""
    match = _BG_URL_RE.search(style)
    if not match or _BG_SHORTHAND_RE.search(style, match.end()):
        return None
    return match.group(2).strip() or None


def classify_url(url):
    """``(kind, ref)`` of a background URL.

    ``("attachment", id)`` for ``/web/image|content/<id>`` and
    ``/web/image/ir.attachment/<id>/datas``; ``("company", (id, field))``
    and ``("partner", (id, field))`` for a record image; ``("external",
    None)`` for an ``http(s)://`` picture; ``("other", None)`` for anything
    else (the stock snippet images); ``("none", None)`` without URL.
    """
    if not url:
        return "none", None
    match = _RECORD_URL_RE.match(url)
    if match:
        kind = "company" if match.group(1) == "res.company" else "partner"
        return kind, (int(match.group(2)), match.group(3))
    match = _ATTACHMENT_URL_RE.match(url)
    if match:
        return "attachment", int(match.group(1))
    if _EXTERNAL_URL_RE.match(url):
        return "external", None
    return "other", None


def first_h2(section):
    """Text of the first ``<h2>`` of the section, not of a nested one."""
    for h2 in section.iter("h2"):
        if next(h2.iterancestors("section"), None) is section:
            return _text(h2)
    return ""


def about_columns(section):
    """``{slot: text}`` of the top-level ``Column`` divs of ``Acerca``."""
    columns = [
        div
        for div in section.xpath(".//div[@data-name='Column']")
        if not div.xpath("ancestor::div[@data-name='Column']")
    ]
    numbers = []
    for column in columns:
        ids = (_COLUMN_ID_RE.match(i) for i in column.xpath(".//div/@id"))
        numbers.append(next((int(m.group(1)) for m in ids if m), None))
    if all(number is None for number in numbers):
        numbers = range(1, len(columns) + 1)
    texts = {}
    for column, number in zip(columns, numbers, strict=True):
        if number is None or number in texts:
            continue
        body = column.xpath(_CARD_BODY)
        texts[number] = _text(body[0]) if body else ""
    return texts


def read_static_homepage(arch):
    """What a static homepage shows.

    :return: ``{"images": {slot: (kind, ref)}, "intro_title", "about",
        "services", "strip_title"}``; a slot whose section is missing is
        ``("none", None)``. An unreadable arch shows nothing.
    """
    result = {
        "images": dict.fromkeys(SLOT_SECTIONS, ("none", None)),
        "intro_title": "",
        "about": "",
        "services": "",
        "strip_title": "",
    }
    try:
        tree = etree.fromstring((arch or "").encode(), safe_parser())
    except etree.XMLSyntaxError:
        return result
    sections = {slot: _section(tree, names) for slot, names in SLOT_SECTIONS.items()}
    for slot, section in sections.items():
        if section is not None:
            result["images"][slot] = classify_url(background_url(section))
    if sections["intro"] is not None:
        result["intro_title"] = first_h2(sections["intro"])
    if sections["strip"] is not None:
        result["strip_title"] = first_h2(sections["strip"])
    about = _section(tree, (ABOUT_SECTION,))
    if about is not None:
        columns = about_columns(about)
        result["about"] = columns.get(1, "")
        result["services"] = columns.get(2, "")
    return result
