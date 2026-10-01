# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Point the values of a legacy microsite homepage at the company.

The 2026 importer wrote ~207 shop homepages as static HTML: phone, address,
email, map, parking and delivery were typed into the arch, so the merchant's
content editor saved the company and the page never changed. This module
rewrites only the VALUE nodes of such an arch into ``t-call``s of small live
templates (and the map ``iframe`` into a ``t-att-src``), leaving the design,
the long texts and the labels -- and therefore their translations -- alone.

Pure lxml, no Odoo import: the transformation can be dry-run against real
arches outside a server. :func:`relink_live_data` is the entry point.

The live templates mark what they render with ``data-cc-live="<kind>"``.
When the website builder saves a page it writes the RENDERED html back into
the arch, so a ``t-call`` becomes literal text again; the marker is how this
module finds such a flattened block and puts the ``t-call`` back.
"""

import html
import re
import unicodedata

from lxml import etree

from .safe_url import safe_http_url

MODULE = "partner_microsite_manager"
LIVE_ATTR = "data-cc-live"
# Marks a feature column this module took over outside the standard
# "Horario" section (it survives a builder save, unlike ``t-if``).
CARD_ATTR = "data-cc-card"

# The static hours card of the first importer generation, swapped by
# 19.0.2.8.0 (``res.company._relink_legacy_opening_hours_card``).
LEGACY_HOURS_CARD_CLASS = "horario-card-accordion"
OPENING_HOURS_CARD_TEMPLATE = f"{MODULE}.microsite_opening_hours_card"
# What the hours card renders as its root: recognises a flattened card.
OPENING_HOURS_CARD_CLASS = "o_microsite_hours"

LIVE_TEMPLATES = {
    "address": f"{MODULE}.microsite_live_address",
    "phone": f"{MODULE}.microsite_live_phone",
    "phone2": f"{MODULE}.microsite_live_phone2",
    "email": f"{MODULE}.microsite_live_email",
    "website": f"{MODULE}.microsite_live_website",
    "parking": f"{MODULE}.microsite_live_parking",
    "delivery": f"{MODULE}.microsite_live_delivery",
    "hours": OPENING_HOURS_CARD_TEMPLATE,
    "hours_label": f"{MODULE}.microsite_live_hours_label",
}

# Contact lines in page order, with the icon that identifies each one
# (``<p class="mb-2"><i class="fa fa-phone fa-fw ..."/>928 ...</p>``). The
# importer wrote the second public phone as a second phone line.
CONTACT_LINES = (
    ("address", "fa-map-marker"),
    ("phone", "fa-phone"),
    ("phone2", "fa-phone"),
    ("email", "fa-envelope"),
    ("website", "fa-globe"),
)
# The values that may legitimately differ between the page and the company.
CONDITIONAL_KINDS = frozenset({"address", "email", "website"})
# Feature cards of the "Horario" section, by their icon.
FEATURE_CARDS = (
    ("hours", "fa-clock-o"),
    ("parking", "fa-map-marker"),
    ("delivery", "fa-truck"),
)

# Shown when the company has the value, and always while the page is being
# edited: the builder saves what it renders, so a card hidden in the editor
# would be gone from the arch for good.
VISIBLE_EXPR = "website.company_id.sudo()._microsite_live_has('{kind}') or editable"
MAP_SRC_EXPR = "website.company_id.sudo()._get_microsite_map_url()"


def _xpath_class(name):
    return f"contains(concat(' ', normalize-space(@class), ' '), ' {name} ')"


def safe_parser():
    """No entity expansion, no network: an arch is data, never a fetch."""
    return etree.XMLParser(resolve_entities=False, no_network=True)


def _tcall(kind, tail=None):
    call = etree.Element("t")
    call.set("t-call", LIVE_TEMPLATES[kind])
    call.tail = tail
    return call


def _is_tcall(element, kind):
    return element.tag == "t" and element.get("t-call") == LIVE_TEMPLATES[kind]


def _remove_keep_tail(element):
    """Drop ``element`` but keep the text that followed it."""
    parent = element.getparent()
    if element.tail:
        previous = element.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or "") + element.tail
        else:
            parent.text = (parent.text or "") + element.tail
    parent.remove(element)


def _set_visibility(element, kind):
    element.set("t-if", VISIBLE_EXPR.format(kind=kind))


def _set_content(element, kind, after=None):
    """Make the content of ``element`` (after the ``after`` child, when
    given) exactly one ``t-call`` of the live template ``kind``."""
    if after is None:
        element.text = None
        for child in list(element):
            element.remove(child)
    else:
        after.tail = None
        for child in list(after.itersiblings()):
            element.remove(child)
    element.append(_tcall(kind))


def _content_is(element, kind, after=None):
    """Whether ``_set_content`` would leave ``element`` as it is."""
    children = list(element)
    if after is None:
        return not (element.text or "").strip() and (
            len(children) == 1 and _is_tcall(children[0], kind)
        )
    following = list(after.itersiblings())
    return (
        not (after.tail or "").strip()
        and len(following) == 1
        and _is_tcall(following[0], kind)
        and not (following[0].tail or "").strip()
    )


def restore_flattened_blocks(tree):
    """Put the ``t-call`` back wherever the builder saved a rendered live
    block. Returns the kinds restored."""
    restored = []
    for element in tree.xpath(f"//*[@{LIVE_ATTR}]"):
        kind = element.get(LIVE_ATTR)
        if kind == "map" or kind not in LIVE_TEMPLATES:
            continue
        if element.getparent() is None:
            continue
        element.getparent().replace(element, _tcall(kind, element.tail))
        restored.append(kind)
    # A card flattened before it carried the marker.
    for element in tree.xpath(f"//div[{_xpath_class(OPENING_HOURS_CARD_CLASS)}]"):
        parent = element.getparent()
        if parent is None:
            continue
        parent.replace(element, _tcall("hours", element.tail))
        restored.append("hours")
    return restored


def swap_legacy_hours_cards(tree):
    """Replace the first-generation static hours card(s) with the t-call.
    Returns whether anything was replaced (shared with 19.0.2.8.0)."""
    replaced = False
    for card in tree.xpath(f"//*[{_xpath_class(LEGACY_HOURS_CARD_CLASS)}]"):
        parent = card.getparent()
        if parent is None:
            # A card nested inside a card already swapped out.
            continue
        parent.replace(card, _tcall("hours", card.tail))
        replaced = True
    return replaced


def _wrap(tree):
    found = tree.xpath("//div[@id='wrap']")
    return found[0] if found else tree


def _contact_root(tree, wrap):
    """The top-level section holding the contact form, or ``None``."""
    forms = tree.xpath("//section[@data-name='Formulario']")
    if not forms:
        return None
    root = forms[0]
    for ancestor in forms[0].iterancestors():
        if ancestor is wrap:
            break
        if ancestor.tag == "section":
            root = ancestor
    return root


def _line_icon_kinds(line):
    """The contact kinds whose icon appears in ``line``."""
    kinds = set()
    for icon in line.xpath(f".//i[{_xpath_class('fa-fw')}]"):
        classes = set((icon.get("class") or "").split())
        kinds |= {kind for kind, icon_class in CONTACT_LINES if icon_class in classes}
    kinds.discard("phone2")
    return kinds


def _find_contact_lines(root, report=None):
    """``{kind: [(line, icon), ...]}`` for the contact lines in ``root``.

    A line that is not one plain value -- icons of several kinds in one
    element, or a ``strong``/``b`` label before the value -- is someone's
    own layout; it is left alone (and noted in ``report``).
    """
    found = {}
    refused = []
    for kind, icon_class in CONTACT_LINES:
        if kind == "phone2":
            continue
        icons = root.xpath(f".//i[{_xpath_class(icon_class)}][{_xpath_class('fa-fw')}]")
        for icon in icons:
            line = icon.getparent()
            if line is None or line.tag not in ("p", "div", "li", "span"):
                continue
            if any(line is known for known, _icon in found.get(kind, [])):
                continue
            if any(line is known for known in refused):
                continue
            if len(_line_icon_kinds(line)) > 1:
                refused.append(line)
                if report is not None:
                    report["notes"].append("line with several icons left as is")
                continue
            if line.xpath("./strong|./b"):
                refused.append(line)
                if report is not None:
                    report["notes"].append(f"labelled {kind} line left as is")
                continue
            found.setdefault(kind, []).append((line, icon))
    phones = found.pop("phone", [])
    if phones:
        found["phone"] = phones[:1]
    if phones[1:]:
        found["phone2"] = phones[1:]
    return found


# ----------------------------------------------------------------------
# What the page shows vs. what the company says (migration only)
# ----------------------------------------------------------------------
# Street-type abbreviations, read as the word they stand for: a different
# street type is a different address ("Av. Mayor" is not "Calle Mayor").
_STREET_TYPE_ALIASES = {
    "calles": "calle",
    "cl": "calle",
    "av": "avenida",
    "avda": "avenida",
    "avd": "avenida",
    "pza": "plaza",
    "pl": "plaza",
    "ctra": "carretera",
    "ps": "paseo",
    "po": "paseo",  # "Pº" once the accent marks are gone
}
# Words that say nothing about WHICH address it is: connectors, number
# markers and the country. Single letters count ("Bloque C").
_CONNECTORS = frozenset("de del la las el los y".split())
_NUMBER_MARKERS = frozenset("numero num no".split())
_COUNTRY = frozenset({"espana"})
_ZIP_RE = re.compile(r"^\d{5}$")


def _plain(text):
    text = html.unescape(text or "").replace("\xa0", " ")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def _words(text):
    return [word for word in re.split(r"[^0-9a-z]+", _plain(text)) if word]


def _address_words(text):
    """``_words`` with "s/n" as one word and "C/" / "C." read as calle."""
    plain = _plain(text)
    plain = re.sub(r"\bs\s*/\s*n\b", " sn ", plain)
    plain = re.sub(r"(^|[\s,;(])c\s*[/.]\s*", r"\1calle ", plain)
    words = [word for word in re.split(r"[^0-9a-z]+", plain) if word]
    return [_STREET_TYPE_ALIASES.get(word, word) for word in words]


def address_tokens(text):
    """The tokens that tell an address apart: no accents, case or
    punctuation; street types canonical; no connectors, number markers,
    zips or country. Street type, name, number and city all count."""
    dropped = _CONNECTORS | _NUMBER_MARKERS | _COUNTRY
    return {
        word
        for word in _address_words(text)
        if word not in dropped and not _ZIP_RE.match(word)
    }


def _zips(text):
    return {word for word in _words(text) if _ZIP_RE.match(word)}


def address_verdict(shown, live):
    """``None`` when the typed address may become the live one, else why not.

    Relinked when every token the page shows is in the live address (street
    + street2 + zip + city): the contact says the same or more, so a page
    showing only the city gets the street -- but only if the contact names
    the same city. A zip the page shows must be the contact's zip.
    ``live_poorer`` when the live address says strictly less (the street or
    the number would be lost), ``differs`` otherwise. With no token on
    either side, the texts must match, zips aside.
    """
    shown_zips = _zips(shown)
    if shown_zips and not shown_zips <= _zips(live):
        return "differs"
    shown_tokens, live_tokens = address_tokens(shown), address_tokens(live)
    if not shown_tokens and not live_tokens:

        def places(text):
            return [word for word in _words(text) if not _ZIP_RE.match(word)]

        return None if places(shown) == places(live) else "differs"
    if shown_tokens <= live_tokens:
        return None
    if live_tokens < shown_tokens:
        return "live_poorer"
    return "differs"


def _digits(value):
    return re.sub(r"\D", "", value or "")


def _extra_is_duplicate(kind, shown, live):
    """Whether a second static line of ``kind`` shows nothing the live line
    does not (so dropping it loses nothing)."""
    if not live:
        return False
    if kind in ("phone", "phone2"):
        numbers = {_digits(live.get("phone")), _digits(live.get("phone2"))} - {""}
        return bool(_digits(shown)) and _digits(shown) in numbers
    if kind == "email":
        return _same_email(shown, live.get("email"))
    if kind == "address":
        value = live.get("address") or ""
        return bool(value.strip()) and address_verdict(shown, value) is None
    if kind == "website":
        return _same_website(shown, live.get("website"))
    return False


def _same_email(shown, live):
    def norm(value):
        return re.sub(r"\s+", "", value or "").lower()

    return bool(norm(live)) and norm(shown) == norm(live)


def normalize_website(value):
    """A web address as compared: http(s) only, no scheme, no ``www.``, no
    trailing slash, lower case (``""`` when not a usable link)."""
    url = safe_http_url(value).lower()
    url = re.sub(r"^https?://", "", url)
    url = re.sub(r"^www\.", "", url)
    return url.rstrip("/")


def _same_website(shown, live):
    return bool(normalize_website(live)) and (
        normalize_website(shown) == normalize_website(live)
    )


def _line_shown(line, icon, kind):
    """What a static line shows (the href for a web line)."""
    if kind == "website":
        links = line.xpath(".//a/@href")
        if links:
            return links[0].strip()
    parts = [icon.tail or ""]
    for sibling in icon.itersiblings():
        if isinstance(sibling.tag, str):
            parts.append("".join(sibling.itertext()))
        parts.append(sibling.tail or "")
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def _static_verdict(kind, shown, live):
    """``None`` when the static value may become live, else the reason."""
    value = (live or {}).get(kind) or ""
    if not value.strip():
        return "live_empty"
    if kind == "email":
        return None if _same_email(shown, value) else "differs"
    if kind == "address":
        return address_verdict(shown, value)
    if kind == "website":
        return None if _same_website(shown, value) else "differs"
    return None


def _keep_static(report, kind, shown, live, reason):
    report["kept_static"].append(
        {
            "kind": kind,
            "shown": shown,
            "live": (live or {}).get(kind) or "",
            "reason": reason,
        }
    )


def _line_is_live(line, kind):
    return bool(line.xpath(f".//t[@t-call='{LIVE_TEMPLATES[kind]}']"))


def _relink_contact(root, report, live, force, decisions):
    """Relink the contact lines. Returns the kinds that are live after."""
    lines = _find_contact_lines(root, report)
    live_kinds = set()
    report["present"].extend(kind for kind in CONDITIONAL_KINDS if lines.get(kind))
    for kind, _icon_class in CONTACT_LINES:
        entries = lines.get(kind, [])
        if not entries:
            continue
        line, icon = entries[0]
        if _relink_contact_line(line, icon, kind, report, live, force, decisions):
            live_kinds.add(kind)
            _settle_extra_lines(entries[1:], kind, report, live, decisions)
    return live_kinds


def _relink_contact_line(line, icon, kind, report, live, force, decisions):
    """Make the first line of ``kind`` live when the rules allow; returns
    whether it is live afterwards."""
    if kind in CONDITIONAL_KINDS and not _line_is_live(line, kind):
        if kind not in force:
            if decisions is not None:
                # Decided on the copy the page was written in.
                if decisions.get(kind) != "relink":
                    return False
            elif live is None:
                # A builder save: a static line stays static.
                return False
            else:
                shown = _line_shown(line, icon, kind)
                reason = _static_verdict(kind, shown, live)
                if reason:
                    _keep_static(report, kind, shown, live, reason)
                    return False
    unchanged = _content_is(line, kind, after=icon) and line.get(
        "t-if"
    ) == VISIBLE_EXPR.format(kind=kind)
    if not unchanged:
        _set_content(line, kind, after=icon)
        _set_visibility(line, kind)
        report["relinked"].append(kind)
    return True


def _settle_extra_lines(extras, kind, report, live, decisions):
    """More static lines of a kind whose first line is live: dropped only
    when they show nothing the live line does not; kept (and noted)
    otherwise. Never decided on a builder save or a human edit."""
    for number, (extra, extra_icon) in enumerate(extras, 1):
        key = f"{kind}#{number}"
        if decisions is not None:
            duplicate = decisions.get(key) == "drop"
        elif live is not None:
            duplicate = _extra_is_duplicate(
                kind, _line_shown(extra, extra_icon, kind), live
            )
            report["extras"][key] = "drop" if duplicate else "keep"
        else:
            duplicate = False
        if duplicate:
            _remove_keep_tail(extra)
            report["dropped"].append(kind)
        else:
            report["notes"].append(f"extra {kind} line kept as typed")


def _relink_map(root, report, live, force, address_live, decisions):
    # The importer's map, or its empty shell (a few shops had no address
    # when they were imported and got ``src=""``). Only inside the contact
    # block.
    iframes = root.xpath(
        f".//iframe[@{LIVE_ATTR}='map' or @t-att-src or normalize-space(@src)=''"
        " or contains(@src, 'maps.google') or contains(@src, 'google.com/maps')"
        " or contains(@src, 'goo.gl')]"
    )
    if not iframes:
        report["notes"].append("no map iframe")
    else:
        report["present"].append("map")
    wanted = {
        LIVE_ATTR: "map",
        "t-att-src": MAP_SRC_EXPR,
        "t-if": VISIBLE_EXPR.format(kind="map"),
    }
    for iframe in iframes:
        is_live = iframe.get(LIVE_ATTR) == "map" or iframe.get("t-att-src")
        if not is_live and "map" not in force:
            if decisions is not None:
                if decisions.get("map") != "relink":
                    continue
            elif live is None:
                continue
            # The address fallback must match the address the page shows:
            # without the shop's own map link, the static map stays unless
            # the address line went live.
            elif not (live.get("map_explicit") or address_live):
                _keep_static(
                    report,
                    "map",
                    iframe.get("src") or "",
                    {"map": live.get("map") or ""},
                    "no_map_url_and_address_static",
                )
                continue
        if "src" not in iframe.attrib and all(
            iframe.get(k) == v for k, v in wanted.items()
        ):
            continue
        iframe.attrib.pop("src", None)
        for name, value in wanted.items():
            iframe.set(name, value)
        report["relinked"].append("map")


def _elements(element):
    """Element children, comments and processing instructions left out."""
    return [child for child in element if isinstance(child.tag, str)]


def _feature_columns(section):
    columns = {}
    for kind, icon_class in FEATURE_CARDS:
        for column in section.xpath(f".//div[{_xpath_class('row')}]/div"):
            if column.xpath(f"./span[{_xpath_class(icon_class)}]"):
                columns.setdefault(kind, column)
    return columns


def _only_known_columns(section, columns):
    """Whether the section is nothing but the importer's (up to) three
    cards: only then may hiding it as a whole hide nothing else."""
    rows = section.xpath(f".//div[{_xpath_class('row')}]")
    if len(rows) != 1:
        return False
    known = list(columns.values())
    return all(any(child is column for column in known) for child in _elements(rows[0]))


def _relink_hours_column(column, report, label_tags=("h5", "h6")):
    expected = VISIBLE_EXPR.format(kind="hours")
    calls = [c for c in column if _is_tcall(c, "hours")]
    changed = False
    if not calls:
        labels = [c for c in column if c.tag in label_tags]
        if labels:
            _set_content(column, "hours", after=labels[0])
        else:
            column.append(_tcall("hours"))
        changed = True
    if column.get("t-if") != expected:
        column.set("t-if", expected)
        changed = True
    if changed:
        report["relinked"].append("hours")


def _relink_value_column(column, kind, report):
    expected = VISIBLE_EXPR.format(kind=kind)
    values = column.xpath("./p")
    changed = False
    if values:
        value = values[0]
        if not _content_is(value, kind):
            _set_content(value, kind)
            changed = True
        for extra in values[1:]:
            _remove_keep_tail(extra)
            changed = True
    else:
        value = etree.Element("p")
        value.set("class", "text-muted")
        value.append(_tcall(kind))
        labels = column.xpath("./h5|./h6")
        if labels:
            labels[0].addnext(value)
        else:
            column.append(value)
        changed = True
    if column.get("t-if") != expected:
        column.set("t-if", expected)
        changed = True
    if changed:
        report["relinked"].append(kind)


def _relink_features(tree, facts, report, insert_missing):
    """The "Horario" features section, the "Info Bar" variant, or a new
    minimal hours section. Returns nothing; fills ``report``."""
    sections = tree.xpath("//section[@data-name='Horario']")
    if sections:
        section = sections[0]
        columns = _feature_columns(section)
        if "hours" in columns:
            _relink_hours_column(columns["hours"], report)
        elif facts.get("hours"):
            report["notes"].append("Horario section without an hours card")
        for kind in ("parking", "delivery"):
            if kind in columns:
                _relink_value_column(columns[kind], kind, report)
        expected = VISIBLE_EXPR.format(kind="features")
        if not _only_known_columns(section, columns):
            report["notes"].append("Horario section has other content: no t-if")
        elif section.get("t-if") != expected:
            section.set("t-if", expected)
            report["relinked"].append("features")
        return
    # Second importer generation ("Info Bar"): the hours as static markup
    # in a column carrying the week as JSON. Once relinked the column keeps
    # a marker of its own, so a later builder save cannot lose it.
    info_columns = tree.xpath(f"//*[@data-horario-info or @{CARD_ATTR}='hours']")
    if info_columns:
        column = info_columns[0]
        column.attrib.pop("data-horario-info", None)
        column.set(CARD_ATTR, "hours")
        _relink_hours_column(column, report)
        return
    if tree.xpath(f"//t[@t-call='{OPENING_HOURS_CARD_TEMPLATE}']"):
        return
    if not insert_missing or not facts.get("hours"):
        return
    anchor = tree.xpath("//section[@data-name='Acerca']")
    if not anchor:
        wrap = _wrap(tree)
        contact = _contact_root(tree, wrap)
        anchor = [contact] if contact is not None else []
    if not anchor:
        report["notes"].append("no place for the hours card")
        return
    anchor[0].addprevious(_new_hours_section(anchor[0]))
    report["inserted"].append("hours")


def _new_hours_section(anchor):
    section = etree.Element("section")
    section.set("class", "s_features pt48 pb48")
    section.set("data-snippet", "s_features")
    section.set("data-name", "Horario")
    section.set("t-if", VISIBLE_EXPR.format(kind="features"))
    container = etree.SubElement(section, "div", {"class": "container"})
    row = etree.SubElement(container, "div", {"class": "row justify-content-center"})
    column = etree.SubElement(
        row,
        "div",
        {
            "class": "col-lg-4 pt16 pb16 text-center",
            "t-if": VISIBLE_EXPR.format(kind="hours"),
        },
    )
    etree.SubElement(
        column,
        "span",
        {
            "class": "fa fa-clock-o fa-2x mb-3",
            "style": "display: block; color: var(--o-color-1);",
        },
    )
    label = etree.SubElement(column, "h5", {"class": "fw-bold"})
    label.append(_tcall("hours_label"))
    column.append(_tcall("hours"))
    section.tail = anchor.tail
    return section


def empty_report():
    return {
        "relinked": [],
        "inserted": [],
        "dropped": [],
        "restored": [],
        "kept_static": [],
        "present": [],
        "extras": {},
        "notes": [],
        "skipped": None,
    }


def relink_live_data(
    arch, facts, insert_missing=False, live=None, force=(), decisions=None
):
    """Relink the values of a legacy homepage ``arch``.

    Phone, second phone, parking, delivery and hours always become live.
    Email, address, web and map are what may differ between the page and
    the company (a shop address vs. a fiscal one, a public mailbox vs. a
    login), so a STATIC line of those kinds becomes live only:

    - in the migration (``live`` given), when it shows what the company
      says (see ``_static_verdict``); otherwise it is kept and reported in
      ``report["kept_static"]``. The map follows when the shop has its own
      map link or its address line went live;
    - when a human just changed that value (``force``);
    - never on a builder save (neither given): a static line stays static.

    A line or iframe that is already live (or that the builder flattened) is
    always kept live.

    :param str arch: the base (``en_US``) arch of the page view
    :param dict facts: ``{kind: bool}`` -- which values the company has
    :param bool insert_missing: add the hours card a page lacks while the
        shop has hours (the migration only; contact lines are never added)
    :param dict live: the company's ``email``, ``address``, ``website``,
        ``map`` values and ``map_explicit`` (migration only)
    :param force: kinds to make live whatever the page shows
    :param dict decisions: ``{kind: "relink"|"keep"}`` for the static email,
        address, web and map lines, taken beforehand on another language
        copy of the page (:func:`decide_contact_kinds`); a kind missing from
        it stays static
    :returns: ``(new_arch or None, report)``; ``None`` when nothing changes
        or the page is skipped (``report["skipped"]`` says why)
    """
    report = empty_report()
    force = frozenset(force or ())
    tree = etree.fromstring(arch.encode("utf-8"), parser=safe_parser())
    before = etree.tostring(tree, encoding="unicode")
    wrap = _wrap(tree)
    contact = _contact_root(tree, wrap)
    if contact is None:
        report["skipped"] = "no contact block (section Formulario)"
        return None, report
    if not _find_contact_lines(contact):
        report["skipped"] = "no contact lines (address/phone/email icons)"
        return None, report
    report["restored"] = restore_flattened_blocks(tree)
    if swap_legacy_hours_cards(tree):
        report["relinked"].append("hours")
    live_kinds = _relink_contact(contact, report, live, force, decisions)
    _relink_map(contact, report, live, force, "address" in live_kinds, decisions)
    _relink_features(tree, facts, report, insert_missing)
    for key in ("relinked", "inserted", "dropped", "restored", "notes", "present"):
        report[key] = list(dict.fromkeys(report[key]))
    after = etree.tostring(tree, encoding="unicode")
    if after == before:
        return None, report
    return after, report


def decide_contact_kinds(arch, facts, live):
    """Keep or relink each static email/address/web/map line, judged on
    ``arch`` -- the copy in the language the page was written in.

    The migration writes the base (``en_US``) arch, but the importer's
    ``en_US`` copies hold machine translations of the values
    ("adgconditioning", "The Palms of Gran Canaria"): comparing those with
    the company would keep almost every line static. Returns
    ``(decisions, report)``; ``report["kept_static"]`` carries what that
    copy shows, for the review list.
    """
    _new_arch, report = relink_live_data(arch, facts, live=live)
    kept = {entry["kind"] for entry in report["kept_static"]}
    decisions = {
        kind: "keep" if kind in kept else "relink"
        for kind in report["present"]
        if kind in CONDITIONAL_KINDS or kind == "map"
    }
    decisions.update(report["extras"])
    return decisions, report
