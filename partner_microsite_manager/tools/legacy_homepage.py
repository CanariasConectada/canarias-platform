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

from lxml import etree

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
_ICONS = {icon for _kind, icon in CONTACT_LINES}
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


def _find_contact_lines(root):
    """``{kind: [(line, icon), ...]}`` for the contact lines in ``root``."""
    found = {}
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
            found.setdefault(kind, []).append((line, icon))
    phones = found.pop("phone", [])
    if phones:
        found["phone"] = phones[:1]
    if phones[1:]:
        found["phone2"] = phones[1:]
    return found


def _new_line(template_line, template_icon, icon_class, kind):
    """A line shaped like ``template_line`` for ``kind``."""
    line = etree.Element(template_line.tag)
    for name, value in template_line.attrib.items():
        if name != "t-if":
            line.set(name, value)
    icon = etree.SubElement(line, "i")
    classes = [
        icon_class if c in _ICONS else c
        for c in (template_icon.get("class") or "fa fa-fw").split()
    ]
    icon.set("class", " ".join(classes))
    line.append(_tcall(kind))
    _set_visibility(line, kind)
    line.tail = template_line.tail
    return line


def _relink_contact(root, facts, report):
    lines = _find_contact_lines(root)
    if not any(lines.get(kind) for kind in ("address", "phone", "email")):
        return False
    for kind, _icon_class in CONTACT_LINES:
        entries = lines.get(kind, [])
        for line, _icon in entries[1:]:
            # The live line already shows every value of its kind (both
            # phones, for one); a second static copy would show it twice.
            _remove_keep_tail(line)
            report["dropped"].append(kind)
        if not entries:
            continue
        line, icon = entries[0]
        unchanged = _content_is(line, kind, after=icon) and line.get(
            "t-if"
        ) == VISIBLE_EXPR.format(kind=kind)
        if not unchanged:
            _set_content(line, kind, after=icon)
            _set_visibility(line, kind)
            report["relinked"].append(kind)
    # Lines the page never had (or lost) while the company has the value.
    present = {kind for kind, entries in lines.items() if entries}
    sample_line, sample_icon = next(
        lines[kind][0] for kind, _i in CONTACT_LINES if lines.get(kind)
    )
    order = [kind for kind, _i in CONTACT_LINES]
    for index, (kind, icon_class) in enumerate(CONTACT_LINES):
        if kind in present or not facts.get(kind):
            continue
        new_line = _new_line(sample_line, sample_icon, icon_class, kind)
        before = [k for k in order[:index] if k in present]
        after = [k for k in order[index + 1 :] if k in present]
        if before:
            anchor = lines[before[-1]][0][0]
            anchor.addnext(new_line)
            # addnext moves the anchor's tail onto the new line; keep the
            # anchor's own whitespace.
            anchor.tail, new_line.tail = new_line.tail, anchor.tail
        else:
            lines[after[0]][0][0].addprevious(new_line)
        lines[kind] = [(new_line, new_line[0])]
        present.add(kind)
        report["inserted"].append(kind)
    return True


def _relink_map(root, report):
    # The importer's map, or its empty shell (a few shops had no address
    # when they were imported and got ``src=""``).
    iframes = root.xpath(
        f".//iframe[@{LIVE_ATTR}='map' or normalize-space(@src)=''"
        " or contains(@src, 'maps.google') or contains(@src, 'google.com/maps')"
        " or contains(@src, 'goo.gl')]"
    )
    for iframe in iframes:
        wanted = {
            LIVE_ATTR: "map",
            "t-att-src": MAP_SRC_EXPR,
            "t-if": VISIBLE_EXPR.format(kind="map"),
        }
        if "src" not in iframe.attrib and all(
            iframe.get(k) == v for k, v in wanted.items()
        ):
            continue
        iframe.attrib.pop("src", None)
        for name, value in wanted.items():
            iframe.set(name, value)
        report["relinked"].append("map")
    if not iframes:
        report["notes"].append("no map iframe")


def _feature_columns(section):
    columns = {}
    for kind, icon_class in FEATURE_CARDS:
        for column in section.xpath(f".//div[{_xpath_class('row')}]/div"):
            if column.xpath(f"./span[{_xpath_class(icon_class)}]"):
                columns.setdefault(kind, column)
    return columns


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


def _relink_features(tree, facts, report):
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
        if section.get("t-if") != expected:
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
    if not facts.get("hours"):
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
        "notes": [],
        "skipped": None,
    }


def relink_live_data(arch, facts):
    """Relink the values of a legacy homepage ``arch``.

    :param str arch: the base (``en_US``) arch of the page view
    :param dict facts: ``{kind: bool}`` -- which values the company has
        (``address``, ``phone``, ``email``, ``website``, ``hours``); only
        used to decide whether a line the page lacks is worth adding
    :returns: ``(new_arch or None, report)``; ``None`` when nothing changes
        or the page is skipped (``report["skipped"]`` says why)
    """
    report = empty_report()
    tree = etree.fromstring(arch.encode("utf-8"))
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
    _relink_contact(contact, facts, report)
    _relink_map(contact, report)
    _relink_features(tree, facts, report)
    for key in ("relinked", "inserted", "dropped", "restored"):
        report[key] = list(dict.fromkeys(report[key]))
    after = etree.tostring(tree, encoding="unicode")
    if after == before:
        return None, report
    return after, report
