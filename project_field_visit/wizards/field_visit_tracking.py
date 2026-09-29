# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Second spreadsheet format: the consultants' tracking list.

One row per business with its contact details and the follow-up columns the
consultants keep by hand (appointment status, calls, visit rounds, assigned
consultant...), often split in several sheets (a master list, one sheet per
consultant or per zone). Columns are recognised by their header text, sheet
by sheet. Contact details go to the task's own fields; any other named column
becomes a task property of the phase, so a new column in the sheet needs no
code.
"""

import datetime
import re

from .sheet_utils import as_int, clean, normalize

HEADER_SCAN = 15
MIN_HEADER_CELLS = 3


def header_words(value):
    """Header text reduced to lowercase ascii words."""
    return re.sub(r"[^a-z0-9]+", " ", normalize(value)).strip()


def _alias_match(words, aliases):
    """``words`` equals an alias; an alias ending in ``*`` is a prefix."""
    for alias in aliases:
        if alias.endswith("*"):
            stem = alias[:-1]
            if words == stem or words.startswith(stem + " "):
                return True
        elif words == alias:
            return True
    return False


# The business name, most specific header first: "Nombre" alone is the
# business on a master list but the contact person on a sheet that also has
# a more specific business column ("Descripción", "Nombre beneficiario").
NAME_ALIASES = [
    ("nombre comercial*",),
    ("comercio*",),
    ("razon social*",),
    ("nombre beneficiario*", "beneficiario"),
    ("nombre del comercio", "nombre del negocio", "negocio", "establecimiento"),
    ("empresa",),
    ("descripcion",),
    ("nombre",),
]
CONTACT_ALIASES = (
    "persona de contacto",
    "contacto",
    "nombre de la persona",
    "nombre del contacto",
    "nombre contacto",
    "interlocutor",
)
# Column key -> header aliases.
STANDARD_ALIASES = [
    ("address", ("direccion*", "domicilio", "calle", "ubicacion")),
    ("phone", ("tlf", "telf", "tfno", "telefono*", "telefonos", "movil")),
    ("email", ("correo", "correos", "mail", "email", "e mail", "correo electronico")),
    ("zone", ("zona", "barrio", "zona comercial")),
    (
        "consultant",
        (
            "asignacion",
            "asignado",
            "asignada",
            "asignado a",
            "consultor*",
            "consultora*",
            "tecnico",
            "tecnica",
        ),
    ),
    ("observations", ("observaciones*", "notas", "nota", "comentarios")),
    ("annex_number", ("anexo",)),
    ("subdomain", ("subdominio*",)),
    ("hours", ("horario*", "hora", "horas")),
]
# Dates of the visit rounds (first visit, second round, meeting...). The
# latest is the planned visit; how many are filled, the contact attempts.
DATE_HEADERS = {
    "dia",
    "fecha",
    "fechavisita",
    "fechadevisita",
    "fechadelavisita",
    "fechareunion",
    "fechadelareunion",
    "fechacita",
    "fechadelacita",
    "proximavisita",
}
DATE_ROUND = re.compile(r"^(\d+a?)?(vuelta|visita)s?$")
# A sheet with one of these headers holds credentials: never read it.
SECRET_HEADERS = {"password", "contrasena", "contrasenas", "clave", "claves", "pass"}
SECRET_TITLE = re.compile(r"contrasen|password|clave")
# Personal identifiers are not copied to the task.
IGNORED_HEADERS = {"nif", "cif", "nifcif", "cifnif", "dni", "nie"}
GENERIC_HEADER = re.compile(r"^(column|columna|col|unnamed|campo)( \d+)*$")

# Task properties the tracking format may add to a phase: name -> label.
VISIT_STATUS = ("fv_visit_status", "Estado de visita")
KNOWN_PROPERTIES = {"cita": VISIT_STATUS, "estadodevisita": VISIT_STATUS}
HOURS_PROPERTY = ("fv_hours", "Horario")
CONSULTANT_PROPERTY = ("fv_consultant", "Consultor asignado")
ATTEMPTS_PROPERTY = ("fv_contact_attempts", "Intentos de contacto")

STANDARD_KEYS = ("address", "phone", "email", "zone", "contact", "consultant")


def is_secret_sheet(title):
    return bool(SECRET_TITLE.search(normalize(title)))


def property_label(header):
    """Label of a property from the header as the consultants wrote it."""
    text = clean(header)
    if text.isupper() and len(text) > 4:
        return text.capitalize()
    return text[:1].upper() + text[1:]


def tracking_layout(row):
    """Column layout of a tracking-list header row, or ``None``.

    :return: dict with the column index of ``name`` and of each standard
        key present, ``dates`` (column -> property name for stray text),
        ``props`` (column -> (property name, label)) and ``secret``.
    """
    cells = [(col, header_words(cell), cell) for col, cell in enumerate(row or [])]
    cells = [(col, words, raw) for col, words, raw in cells if words]
    if len(cells) < MIN_HEADER_CELLS:
        return None
    layout = {"dates": {}, "props": {}, "secret": False}
    names = {}
    for col, words, raw in cells:
        key = words.replace(" ", "")
        if key in SECRET_HEADERS:
            layout["secret"] = True
            continue
        if key in IGNORED_HEADERS:
            continue
        if _alias_match(words, CONTACT_ALIASES):
            layout.setdefault("contact", col)
            continue
        rank = next(
            (
                i
                for i, aliases in enumerate(NAME_ALIASES)
                if _alias_match(words, aliases)
            ),
            None,
        )
        if rank is not None:
            names.setdefault(rank, col)
            continue
        standard = next(
            (k for k, aliases in STANDARD_ALIASES if _alias_match(words, aliases)),
            None,
        )
        if standard:
            layout.setdefault(standard, col)
            continue
        if key in DATE_HEADERS or DATE_ROUND.match(key):
            layout["dates"][col] = ("fv_" + key[:40], property_label(raw))
            continue
        if len(re.sub(r"[^a-z]", "", key)) < 3 or GENERIC_HEADER.match(words):
            continue
        layout["props"][col] = KNOWN_PROPERTIES.get(
            key, ("fv_" + key[:40], property_label(raw))
        )
    if not names:
        return None
    ranks = sorted(names)
    layout["name"] = names[ranks[0]]
    # A plain "Nombre" next to a more specific business column is a person.
    if len(ranks) > 1 and ranks[-1] == len(NAME_ALIASES) - 1:
        layout.setdefault("contact", names[ranks[-1]])
    recognised = (
        sum(1 for key in STANDARD_ALIASES if key[0] in layout)
        + len(layout["dates"])
        + ("contact" in layout)
    )
    if not recognised and not layout["secret"]:
        return None
    return layout


def cell_value(value):
    """Typed value of a cell: bool, date, or text."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.time):
        return value.strftime("%H:%M")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = clean(value)
    return parse_date(text) or text or None


def parse_date(text):
    """A date written as text (CSV): ``dd/mm/yyyy`` or ISO."""
    text = clean(text)
    match = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})", text)
    try:
        if match:
            day, month, year = (int(g) for g in match.groups())
            return datetime.date(year + 2000 if year < 100 else year, month, day)
        match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})( .*)?", text)
        if match:
            return datetime.date(*(int(g) for g in match.groups()[:3]))
    except ValueError:
        return None
    return None


def phone_text(value):
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return clean(value)


def parse_tracking_rows(rows, layout, title):
    """Business rows of one tracking sheet.

    :return: (records, skipped); each record has the keys the matching
        needs (``legal_name``, ``trade_name``, ``subdomain``,
        ``annex_number``), the standard keys, ``observations``, ``dates``
        and ``props`` (property name -> typed value).
    """

    def cell(row, col):
        return row[col] if col is not None and col < len(row) else None

    records, skipped = [], 0
    for row in rows:
        name = clean(cell(row, layout["name"]))
        if not name:
            continue
        if len(name) < 2 or not re.search(r"[^\W\d_]", name):
            skipped += 1
            continue
        record = {
            "legal_name": "",
            "trade_name": name,
            "section": None,
            "sheet": clean(title),
            "subdomain": cell(row, layout.get("subdomain")),
            "annex_number": cell(row, layout.get("annex_number")),
            "observations": clean(cell(row, layout.get("observations"))),
            "dates": [],
            "props": {},
            "labels": {},
        }
        for key in STANDARD_KEYS:
            value = cell(row, layout.get(key))
            text = phone_text(value) if key == "phone" else clean(value)
            record[key] = text.lower() if key == "email" else text
        hours = cell_value(cell(row, layout.get("hours")))
        if hours not in (None, ""):
            record["props"][HOURS_PROPERTY[0]] = str(hours)
            record["labels"][HOURS_PROPERTY[0]] = HOURS_PROPERTY[1]
        for col, (prop, label) in layout["dates"].items():
            value = cell_value(cell(row, col))
            if isinstance(value, datetime.date):
                record["dates"].append(value)
            elif value not in (None, ""):
                # Text in a date column ("pasar el viernes"): keep it.
                record["props"][prop] = str(value)
                record["labels"][prop] = label
        for col, (prop, label) in layout["props"].items():
            value = cell_value(cell(row, col))
            if value in (None, ""):
                continue
            record["props"][prop] = value
            record["labels"][prop] = label
        records.append(record)
    return records, skipped


def merge_tracking(target, other):
    """Fold a row of another sheet about the same business into ``target``.

    Sheet order decides: the first sheet that fills a value wins (the master
    list comes first in the client's workbook); dates and notes add up.
    """
    for key in STANDARD_KEYS + ("subdomain", "annex_number"):
        if not target.get(key) and other.get(key):
            target[key] = other[key]
    for prop, value in other["props"].items():
        target["props"].setdefault(prop, value)
        target["labels"].setdefault(prop, other["labels"][prop])
    target["dates"] = sorted(set(target["dates"]) | set(other["dates"]))
    notes = [n for n in (target["observations"], other["observations"]) if n]
    if len(notes) == 2 and notes[1] in notes[0]:
        notes = notes[:1]
    target["observations"] = "\n".join(notes)


def property_type(values):
    """Property type fitting every value found for a column."""
    values = [v for v in values if v not in (None, "")]
    if values and all(isinstance(v, bool) for v in values):
        return "boolean"
    if values and all(isinstance(v, datetime.date) for v in values):
        return "date"
    return "char"


def property_value(value, prop_type):
    """Value of a cell for a property of ``prop_type``."""
    if prop_type == "boolean":
        return bool(value)
    if prop_type == "date":
        return value.isoformat()
    if prop_type == "integer":
        return as_int(value)
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, datetime.date):
        return value.strftime("%d/%m/%Y")
    return str(value)
