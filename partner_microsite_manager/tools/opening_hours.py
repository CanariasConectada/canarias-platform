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
