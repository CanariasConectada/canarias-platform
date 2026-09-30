# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Text helpers shared by both spreadsheet formats of the importer."""

import re
import unicodedata


def normalize(value):
    """Casefolded text without accents, extra spaces or trailing blanks."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return " ".join(text.casefold().split())


def clean(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def as_int(value):
    """Whole number of a cell, numeric or text (CSV); ``None`` otherwise."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return int(value)
    text = clean(value)
    if re.fullmatch(r"\d+(\.0+)?", text):
        return int(float(text))
    return None
