# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Point the cover and the two picture strips of a legacy homepage at the
company.

The importer typed the cover title, the cover button, the titles of the
``SEC1`` (intro) and ``Separador`` (closing) strips and the three background
pictures into the arch, so a merchant saving "Page content" changed the
company and the page kept the importer's text (Zig Zag Merceria: the field
says "Productos", the button "Tienda"). Same mechanism as the contact block
(``tools/legacy_homepage``): the VALUE node becomes a ``t-call`` of a live
template (``views/microsite_live_data.xml``); a background picture becomes
the company-field URL, which always serves the current image.

Pure lxml, no Odoo import. The caller decides which kinds may be relinked
(the migration on what each page shows, a human edit on what changed); this
module only finds the nodes and applies those decisions. A node already
live -- or flattened by a builder save and restored -- is always kept live.
"""

import re

from lxml import etree

from .homepage_completeness import _BG_URL_RE, SLOT_SECTIONS, _section, background_url
from .legacy_homepage import (
    _content_is,
    _elements,
    _set_content,
    empty_report,
    restore_flattened_blocks,
    safe_parser,
)

TEXT_KINDS = ("title", "button", "intro_title", "strip_title")
# Background kind -> (homepage slot, company image field).
IMAGE_KINDS = {
    "hero_bg": ("hero", "microsite_hero_image"),
    "intro_bg": ("intro", "microsite_intro_image"),
    "strip_bg": ("strip", "microsite_banner_image"),
}
COVER_KINDS = frozenset(TEXT_KINDS) | frozenset(IMAGE_KINDS)
# Inline wrappers the builder puts around a heading's text ("<h2><font
# style=...>Title</font></h2>"): the value is the text inside them.
_WRAPPERS = frozenset({"span", "font", "b", "strong", "em"})


def company_image_url(company_id, field):
    return f"/web/image/res.company/{company_id}/{field}"


def _own(section, tag):
    """``tag`` elements of ``section`` that are not inside a nested section."""
    return [
        element
        for element in section.iter(tag)
        if next(element.iterancestors("section"), None) is section
    ]


def _value_node(element):
    """The innermost node holding ``element``'s text, through single inline
    wrappers without text of their own around them."""
    node = element
    while not (node.text or "").strip():
        children = _elements(node)
        if len(children) != 1 or children[0].tag not in _WRAPPERS:
            break
        if (children[0].tail or "").strip():
            break
        node = children[0]
    return node


def cover_nodes(tree):
    """``{kind: value node}`` of the cover title and button and of the two
    strip titles, for those the page has."""
    nodes = {}
    hero = _section(tree, SLOT_SECTIONS["hero"])
    if hero is not None:
        headings = _own(hero, "h1")
        if headings:
            nodes["title"] = _value_node(headings[0])
        # The importer's call to action: one ``.btn`` to the shop. Several
        # candidates are somebody's own layout and stay as typed.
        buttons = [
            a
            for a in _own(hero, "a")
            if a.get("href") == "/shop" and "btn" in (a.get("class") or "").split()
        ]
        if len(buttons) == 1:
            nodes["button"] = _value_node(buttons[0])
    for kind, slot in (("intro_title", "intro"), ("strip_title", "strip")):
        section = _section(tree, SLOT_SECTIONS[slot])
        if section is not None:
            headings = _own(section, "h2")
            if headings:
                nodes[kind] = _value_node(headings[0])
    return nodes


def _text(node):
    return " ".join("".join(node.itertext()).split())


def _is_plain(node):
    """One plain value: text, no markup of its own."""
    return not _elements(node) and bool(_text(node))


def read_cover(arch):
    """What the cover of ``arch`` shows, for the migration's decisions.

    :return: ``{"texts": {kind: text or None}, "live": {kind, ...},
        "backgrounds": {kind: url or None}}``; a text with markup inside it
        (an icon, a line break) is ``None``: it is nobody's single value.
    """
    tree = etree.fromstring(arch.encode("utf-8"), parser=safe_parser())
    restore_flattened_blocks(tree)
    texts, live = {}, set()
    for kind, node in cover_nodes(tree).items():
        if _content_is(node, kind):
            live.add(kind)
            texts[kind] = None
        else:
            texts[kind] = _text(node) if _is_plain(node) else None
    backgrounds = {}
    for kind, (slot, _field) in IMAGE_KINDS.items():
        section = _section(tree, SLOT_SECTIONS[slot])
        if section is not None:
            backgrounds[kind] = background_url(section)
    return {"texts": texts, "live": live, "backgrounds": backgrounds}


def _set_background(section, url):
    """Point the section's ``background-image`` at ``url``; whether it
    changed. Quotes and every other declaration are kept."""
    style = section.get("style") or ""
    match = _BG_URL_RE.search(style)
    if not match or match.group(2).strip() == url:
        return False
    quote = match.group(1) or "'"
    new = f"background-image: url({quote}{url}{quote})"
    section.set("style", style[: match.start()] + new + style[match.end() :])
    return True


def relink_cover(arch, relink=(), backgrounds=None):
    """Relink the cover of a legacy homepage ``arch``.

    :param relink: text kinds (``TEXT_KINDS``) to make live; a kind left
        out stays as typed unless it is already live
    :param dict backgrounds: ``{image kind: url}`` to set as the background
        picture of that section (the caller checked the old one may go)
    :returns: ``(new_arch or None, report)``; ``None`` when nothing changes
    """
    report = empty_report()
    tree = etree.fromstring(arch.encode("utf-8"), parser=safe_parser())
    before = etree.tostring(tree, encoding="unicode")
    report["restored"] = restore_flattened_blocks(tree)
    for kind, node in cover_nodes(tree).items():
        report["present"].append(kind)
        if _content_is(node, kind) or kind not in relink:
            continue
        if not _is_plain(node):
            report["notes"].append(f"{kind} with markup kept as typed")
            continue
        _set_content(node, kind)
        report["relinked"].append(kind)
    for kind, url in (backgrounds or {}).items():
        slot, _field = IMAGE_KINDS[kind]
        section = _section(tree, SLOT_SECTIONS[slot])
        if section is not None and _set_background(section, url):
            report["relinked"].append(kind)
    for key in ("relinked", "restored", "notes", "present"):
        report[key] = list(dict.fromkeys(report[key]))
    after = etree.tostring(tree, encoding="unicode")
    if after == before:
        return None, report
    return after, report


def same_text(shown, value):
    """Whether a page text and a company value read the same."""

    def norm(text):
        return re.sub(r"\s+", " ", text or "").strip()

    return bool(norm(value)) and norm(shown) == norm(value)
