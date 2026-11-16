# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Pure helper to parse the compact opening-hours notation.

The notation is the one merchants already used in the legacy platform:

    ``L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00``

* Day letters are the Spanish initials merchants know:
  ``L M X J V S D`` (Monday..Sunday).
* Each block is ``<days> <start>-<end>``; blocks are separated by ``/``.
* Days can be a range (``L-V``), a comma list (``L,M,J``) or a dash list
  (``L-M-X-J-V``).
* A day may appear in at most two blocks (morning and afternoon shifts).

Kept as a pure module (no Odoo imports) so import scripts can reuse it.
"""

import re

# Day letter -> weekday index (Monday = 0), in merchant notation order.
DAY_LETTERS = ("L", "M", "X", "J", "V", "S", "D")

MAX_RANGES_PER_DAY = 2

_BLOCK_RE = re.compile(r"^([LMXJVSD,\-]+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})$")
_SEPARATOR_RE = re.compile(r"\s*/\s*|\s*·\s*")


def _expand_days(days_token):
    """Expand a day token (``L-V``, ``L,M``, ``L-M-X``) to weekday indexes.

    Returns ``None`` when the token contains an unknown day letter.
    """
    if "-" in days_token and "," not in days_token:
        parts = days_token.split("-")
        if len(parts) == 2:
            # A real range, e.g. L-V.
            try:
                start = DAY_LETTERS.index(parts[0])
                end = DAY_LETTERS.index(parts[1])
            except ValueError:
                return None
            if start > end:
                return None
            return list(range(start, end + 1))
        # A dash-separated list, e.g. L-M-X-J-V-S.
        letters = parts
    else:
        letters = [part.strip() for part in days_token.split(",")]
    try:
        return [DAY_LETTERS.index(letter) for letter in letters if letter]
    except ValueError:
        return None


def parse_opening_hours(value):
    """Parse the compact notation into ``{weekday_index: [(start, end), ...]}``.

    Weekday indexes follow :func:`datetime.date.weekday` (Monday = 0).
    Returns an empty dict for an empty value and ``None`` when the value
    cannot be parsed (so callers can tell "no hours" from "bad format").
    """
    if not value or not str(value).strip():
        return {}
    result = {}
    for block in _SEPARATOR_RE.split(str(value).strip()):
        block = block.strip()
        if not block:
            continue
        match = _BLOCK_RE.match(block)
        if not match:
            return None
        days_token, start, end = match.groups()
        days = _expand_days(days_token)
        if not days:
            return None
        for day in days:
            result.setdefault(day, []).append((start, end))
    return result


# ----------------------------------------------------------------------
# Structured slots <-> compact notation
#
# Since 19.0.2.8.0 the merchant edits opening hours as rows (weekday, opens,
# closes) and the compact text above is GENERATED from them, so the public
# templates keep reading one Char. Times travel as floats in hours (9.5 is
# 09:30), the unit Odoo's ``float_time`` widget speaks.
# ----------------------------------------------------------------------

def hhmm_to_float(value):
    """``'09:30'`` -> ``9.5``."""
    hours, minutes = str(value).split(":")
    return int(hours) + int(minutes) / 60.0


def float_to_hhmm(value):
    """``9.5`` -> ``'09:30'``. Rounded to the minute: ``23:59`` stored as a
    float is ``23.98333...`` and must come back as ``23:59``, not ``23:58``."""
    total = int(round(float(value) * 60))
    hours, minutes = divmod(total, 60)
    return f"{hours:02d}:{minutes:02d}"


def slots_from_parsed(parsed):
    """``{weekday: [(start, end), ...]}`` -> sorted ``[(weekday, open, close)]``.

    Exact duplicates are dropped: the legacy platform accepted ``S,S
    08:00-13:30`` and one shop still carries it, which would otherwise be
    two identical -- and therefore overlapping -- slots.
    """
    slots = set()
    for day, ranges in (parsed or {}).items():
        for start, end in ranges:
            slots.add((int(day), hhmm_to_float(start), hhmm_to_float(end)))
    return sorted(slots)


def format_opening_hours(slots):
    """``[(weekday, open, close), ...]`` -> canonical compact text.

    Consecutive weekdays with identical slots collapse into one day range
    (``L-V``); each range of that run becomes its own block, earliest first;
    blocks are joined with `` / ``. ``L-V 09:00-14:00 / L-V 16:00-20:00 / S
    10:00-13:00`` is what a Monday-to-Friday split shift plus a Saturday
    morning produces -- the very string 54 merchants typed by hand -- and
    :func:`parse_opening_hours` reads it back to the same slots.

    Returns ``""`` for no slots.
    """
    by_day = {}
    for day, open_time, close_time in slots:
        by_day.setdefault(int(day), set()).add(
            (float_to_hhmm(open_time), float_to_hhmm(close_time))
        )
    blocks = []
    days = sorted(by_day)
    index = 0
    while index < len(days):
        start = end = days[index]
        while end + 1 in by_day and by_day[end + 1] == by_day[start]:
            end += 1
        token = (
            DAY_LETTERS[start]
            if start == end
            else f"{DAY_LETTERS[start]}-{DAY_LETTERS[end]}"
        )
        blocks.extend(
            f"{token} {open_time}-{close_time}"
            for open_time, close_time in sorted(by_day[start])
        )
        index = days.index(end) + 1
    return " / ".join(blocks)


def find_slot_problem(slots):
    """First thing wrong with ``[(weekday, open, close), ...]``, or ``None``.

    Returns ``("order", slot)`` when a slot closes before (or when) it opens
    or leaves the 00:00-24:00 day, and ``("overlap", slot_a, slot_b)`` when
    two slots of the same weekday share minutes. Touching slots
    (``09:00-14:00`` then ``14:00-20:00``) are fine.
    """
    ordered = sorted((int(d), float(o), float(c)) for d, o, c in slots)
    for slot in ordered:
        _day, open_time, close_time = slot
        if open_time < 0 or close_time > 24 or open_time >= close_time:
            return ("order", slot)
    for previous, current in zip(ordered, ordered[1:]):
        if previous[0] == current[0] and current[1] < previous[2]:
            return ("overlap", previous, current)
    return None
