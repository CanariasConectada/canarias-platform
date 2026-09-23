#!/usr/bin/env python3
"""Shared helpers for ``aplicar.py`` and ``revertir.py``.

Contents:

* CSV loading and ``campo`` parsing for ``cambios.csv``.
* Pure, regex based arch manipulation for the homepage view
  (``find_section``, ``replace_section_h2``, ``set_section_background``,
  ``insert_sec1_after_hero``, ``extract_section_h2``, ``extract_section_bg``).
  ``find_section`` is depth aware (nested ``<section>`` elements are
  handled). The document is left byte-identical outside the edited span; the
  arch is never parsed with lxml.
* Validation helpers: zip path containment (``zip_image_path``) and the
  background URL whitelist (``check_bg_url``).
* A thin XML-RPC client for Odoo (``OdooClient``). The password is only
  taken from ``ODOO_PASSWORD`` or an interactive prompt, never from a flag.
* Backup file (JSON lines) reading and writing with ``backup`` / ``pending``
  / ``applied`` events.

Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import csv
import getpass
import html
import json
import os
import re
import socket
import sys
import xmlrpc.client
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

HERE = Path(__file__).resolve().parent

DEFAULT_URL = "https://canariasconectada.es"
DEFAULT_DB = "prod"
DEFAULT_CSV = HERE / "cambios.csv"
# Outside the git tree: the backup holds full archs and base64 images.
DEFAULT_BACKUP = Path("/home/odoo/Pending/jev-work/backup.jsonl")
DEFAULT_ZIP_ROOT = Path("/home/odoo/Pending/jev-work/zip/HTML_LIMPIO_WORK_FINAL/COMPLETOS")
DEFAULT_PRIMARY_LANG = "es_ES"

CSV_COLUMNS = ("site", "campo", "valor_anterior", "valor_nuevo", "confianza", "motivo")

COMPANY_IMAGE_FIELDS = ("microsite_hero_image", "microsite_intro_image", "microsite_banner_image")

# Section name -> res.company image field that backs its background image.
SECTION_IMAGE_FIELD = {
    "Hero": "microsite_hero_image",
    "SEC1": "microsite_intro_image",
    "Separador": "microsite_banner_image",
}

MODEL_COMPANY = "res.company"
MODEL_VIEW = "ir.ui.view"
MODEL_PAGE = "website.page"
FIELD_ARCH = "arch_db"

WEB_IMAGE_PREFIX = "/web/image/"
COMPANY_IMAGE_URL_PREFIX = f"{WEB_IMAGE_PREFIX}{MODEL_COMPANY}/"

# The only background URLs that may be written into a view.
_BG_URL_WHITELIST_RE = re.compile(
    r"^/web/image/res\.company/(\d+)/(%s)$" % "|".join(COMPANY_IMAGE_FIELDS))

# Prepended to the ``style`` attribute when a section has no background-image yet.
BG_STYLE_PREFIX = (
    "background-image: url('{url}'); background-size: cover; "
    "background-position: center; background-attachment: fixed; "
)

SEC1_SKELETON = (
    '<section class="s_kickoff o_cc o_cc5 o_colored_level pt104 pb120" '
    'data-snippet="s_kickoff" data-name="SEC1" '
    'style="background-image: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); '
    'background-size: cover; background-position: center; position: relative;">\n'
    '    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; '
    'background: rgba(0,0,0,0.4); z-index: 0;"/>\n'
    '    <div class="container" style="position: relative; z-index: 1;">\n'
    '        <h2 class="h3-fs text-center text-white">{TEXT}</h2>\n'
    "    </div>\n"
    "</section>"
)

# Row kinds, in the order they must be processed inside one site: images are
# uploaded before the backgrounds that reference them, and SEC1 is inserted
# before its heading/background are edited.
KIND_COMPANY_FIELD = "company_field"
KIND_COMPANY_IMAGE = "company_image"
KIND_VIEW_INSERT = "view_insert"
KIND_VIEW_H2 = "view_h2"
KIND_VIEW_BG = "view_bg"
KIND_ORDER = {
    KIND_COMPANY_FIELD: 0,
    KIND_COMPANY_IMAGE: 1,
    KIND_VIEW_INSERT: 2,
    KIND_VIEW_H2: 3,
    KIND_VIEW_BG: 4,
}


class ArchError(ValueError):
    """The arch does not contain what the operation needs."""


class SectionNotFound(ArchError):
    """No ``<section data-name="...">`` with the requested name."""


class CampoError(ValueError):
    """A ``campo`` value in the CSV has an unknown format."""


class OdooError(RuntimeError):
    """Authentication or RPC failure."""


class CredentialsError(OdooError):
    """Login or password could not be obtained."""


# ---------------------------------------------------------------------------
# campo parsing and CSV loading
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Target:
    """Parsed ``campo``: what record and field a CSV row changes."""

    kind: str
    model: str
    field: str
    view_id: int | None = None
    section: str | None = None


_CAMPO_COMPANY_RE = re.compile(r"^res_company\.([A-Za-z_][A-Za-z0-9_]*)$")
_CAMPO_VIEW_RE = re.compile(r"^ir_ui_view\.(\d+)\.([^.]+)\.(h2|bg|insert)$")


def parse_campo(campo: str) -> Target:
    """Parse a ``campo`` string into a :class:`Target`.

    Supported formats::

        res_company.<field>
        ir_ui_view.<view_id>.<SectionName>.h2
        ir_ui_view.<view_id>.<SectionName>.bg
        ir_ui_view.<view_id>.SEC1.insert
    """
    campo = campo.strip()
    m = _CAMPO_COMPANY_RE.match(campo)
    if m:
        field = m.group(1)
        kind = KIND_COMPANY_IMAGE if field in COMPANY_IMAGE_FIELDS else KIND_COMPANY_FIELD
        return Target(kind=kind, model=MODEL_COMPANY, field=field)
    m = _CAMPO_VIEW_RE.match(campo)
    if m:
        view_id, section, op = int(m.group(1)), m.group(2), m.group(3)
        if op == "h2":
            kind = KIND_VIEW_H2
        elif op == "bg":
            kind = KIND_VIEW_BG
        else:
            if section != "SEC1":
                raise CampoError(f"'insert' is only supported for SEC1, got {campo!r}")
            kind = KIND_VIEW_INSERT
        return Target(kind=kind, model=MODEL_VIEW, field=FIELD_ARCH, view_id=view_id, section=section)
    raise CampoError(f"unknown campo format: {campo!r}")


@dataclass
class Change:
    """One row of ``cambios.csv``."""

    site: int
    campo: str
    valor_anterior: str
    valor_nuevo: str
    confianza: float
    motivo: str
    target: Target
    line: int  # 1-based data row number, for messages

    @property
    def row_id(self) -> str:
        return f"{self.site}:{self.campo}"


@dataclass
class InvalidRow:
    """A CSV row that could not be parsed (reported as FAIL, never applied)."""

    line: int
    site: str
    campo: str
    error: str


def load_changes(path: Path) -> tuple[list[Change], list[InvalidRow]]:
    """Load ``cambios.csv``.

    Returns ``(changes, invalid)``. Rows whose ``site``, ``confianza`` or
    ``campo`` cannot be parsed are returned in ``invalid`` instead of raising
    so the caller can report them as failed rows. A missing column raises
    ``ValueError``."""
    changes: list[Change] = []
    invalid: list[InvalidRow] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in CSV_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}; header is {reader.fieldnames}")
        for line, raw in enumerate(reader, start=1):
            site_text = str(raw.get("site") or "").strip()
            campo = (raw.get("campo") or "").strip()
            conf_raw = (raw.get("confianza") or "").strip()
            try:
                site = int(site_text)
            except ValueError:
                invalid.append(InvalidRow(line, site_text, campo, f"site must be an integer, got {site_text!r}"))
                continue
            try:
                confianza = float(conf_raw) if conf_raw else 0.0
            except ValueError:
                invalid.append(InvalidRow(line, site_text, campo, f"confianza must be a number, got {conf_raw!r}"))
                continue
            try:
                target = parse_campo(campo)
            except CampoError as exc:
                invalid.append(InvalidRow(line, site_text, campo, str(exc)))
                continue
            changes.append(Change(
                site=site,
                campo=campo,
                valor_anterior=raw.get("valor_anterior") or "",
                valor_nuevo=raw.get("valor_nuevo") or "",
                confianza=confianza,
                motivo=raw.get("motivo") or "",
                target=target,
                line=line,
            ))
    return changes, invalid


def group_by_site(changes: Iterable[Change]) -> dict[int, list[Change]]:
    """Group rows by site (ascending) and order rows by processing kind."""
    grouped: dict[int, list[Change]] = {}
    for change in changes:
        grouped.setdefault(change.site, []).append(change)
    for rows in grouped.values():
        rows.sort(key=lambda c: (KIND_ORDER[c.target.kind], c.line))
    return dict(sorted(grouped.items()))


def batches(items: list, size: int) -> Iterator[list]:
    """Yield consecutive slices of ``size`` items."""
    if size < 1:
        raise ValueError("batch size must be >= 1")
    for start in range(0, len(items), size):
        yield items[start:start + size]


def parse_site_list(text: str) -> set[int]:
    """Parse ``--only-site 12,34`` into a set of ints."""
    sites = set()
    for part in text.split(","):
        part = part.strip()
        if part:
            sites.add(int(part))
    return sites


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def zip_image_path(zip_root: Path, value: str) -> Path:
    """Resolve an image path from the CSV against ``zip_root``.

    Rejects empty, absolute and ``..`` containing values, and any path that
    resolves (symlinks included) outside ``zip_root``. Raises ``ValueError``.
    The returned path is not checked for existence."""
    value = (value or "").strip()
    if not value:
        raise ValueError("empty image path")
    relative = Path(value)
    if relative.is_absolute() or value.startswith(("/", "\\")):
        raise ValueError(f"absolute image path not allowed: {value!r}")
    if ".." in relative.parts:
        raise ValueError(f"'..' not allowed in image path: {value!r}")
    root = Path(zip_root).resolve()
    resolved = (root / relative).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"image path escapes the zip root: {value!r}")
    return resolved


def check_bg_url(url: str, company_id: int | None = None) -> str:
    """Return an error message when ``url`` is not an allowed background.

    Only ``/web/image/res.company/<id>/<microsite image field>`` is accepted.
    With ``company_id`` the ``<id>`` must match it; with ``None`` (offline)
    only the shape is checked. Returns ``""`` when the URL is acceptable."""
    m = _BG_URL_WHITELIST_RE.match(url or "")
    if not m:
        return (f"background url {url!r} is not allowed; expected "
                f"{COMPANY_IMAGE_URL_PREFIX}<company_id>/<{'|'.join(COMPANY_IMAGE_FIELDS)}>")
    if company_id is not None and int(m.group(1)) != int(company_id):
        return f"background url {url!r} does not belong to company {company_id}"
    return ""


def bg_url_field(url: str) -> str | None:
    """The res.company image field named by an allowed background URL."""
    m = _BG_URL_WHITELIST_RE.match(url or "")
    return m.group(2) if m else None


def company_image_url(company_id: int, field: str) -> str:
    return f"{COMPANY_IMAGE_URL_PREFIX}{int(company_id)}/{field}"


# ---------------------------------------------------------------------------
# Pure arch manipulation
# ---------------------------------------------------------------------------

_SECTION_TOKEN_RE = re.compile(r"<section\b[^>]*>|</section\s*>")
_H2_TOKEN_RE = re.compile(r"<section\b[^>]*>|</section\s*>|<h2\b[^>]*>")
_H2_CLOSE_RE = re.compile(r"</h2\s*>")
_STYLE_RE = re.compile(r"""\sstyle=(["'])(.*?)\1""", re.S)
_BG_URL_RE = re.compile(r"""background-image\s*:\s*url\(\s*(['"]?)(.*?)\1\s*\)""", re.S)
_BG_DECL_RE = re.compile(r"background-image\s*:\s*[^;]*", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class Section:
    """Span of a ``<section data-name="...">...</section>`` inside an arch."""

    name: str
    start: int      # index of "<section"
    open_end: int   # index right after the opening tag's ">"
    end: int        # index right after "</section>"
    arch: str

    def group(self, _index: int = 0) -> str:
        return self.arch[self.start:self.end]

    @property
    def open_tag(self) -> str:
        return self.arch[self.start:self.open_end]

    @property
    def body(self) -> str:
        return self.arch[self.open_end:self.close_start]

    @property
    def close_start(self) -> int:
        return self.arch.rfind("</section", self.open_end, self.end)


def _section_open_re(name: str) -> re.Pattern:
    return re.compile(r'<section\b[^>]*\sdata-name="%s"[^>]*>' % re.escape(name))


def find_section(arch: str, section_name: str) -> Section | None:
    """Locate the first ``<section data-name="NAME">`` and its matching close
    tag, counting nested ``<section>`` opens and closes. Returns ``None`` when
    the section does not exist; raises :class:`ArchError` when its close tag
    is missing."""
    m = _section_open_re(section_name).search(arch)
    if not m:
        return None
    if m.group(0).endswith("/>"):
        return Section(section_name, m.start(), m.end(), m.end(), arch)
    depth = 1
    for token in _SECTION_TOKEN_RE.finditer(arch, m.end()):
        if token.group(0).startswith("</"):
            depth -= 1
            if depth == 0:
                return Section(section_name, m.start(), m.end(), token.end(), arch)
        elif not token.group(0).endswith("/>"):
            depth += 1
    raise ArchError(f"section {section_name!r} has no matching </section>")


def _require_section(arch: str, section_name: str) -> Section:
    section = find_section(arch, section_name)
    if section is None:
        raise SectionNotFound(section_name)
    return section


def _first_h2(section: Section) -> tuple[int, int] | None:
    """(inner_start, inner_end) of the first ``<h2>`` of the section that is
    not inside a nested ``<section>``; absolute indexes into ``section.arch``."""
    depth = 0
    for token in _H2_TOKEN_RE.finditer(section.arch, section.open_end, section.close_start):
        text = token.group(0)
        if text.startswith("</"):
            depth -= 1
        elif text.startswith("<section") and not text.endswith("/>"):
            depth += 1
        elif text.startswith("<h2") and depth == 0:
            if text.endswith("/>"):
                continue
            close = _H2_CLOSE_RE.search(section.arch, token.end(), section.close_start)
            if not close:
                raise ArchError(f"section {section.name!r}: <h2> without </h2>")
            return token.end(), close.start()
    return None


def normalize_text(value) -> str:
    """Collapse whitespace and unescape entities so texts can be compared."""
    if value is None or value is False:
        return ""
    return _WS_RE.sub(" ", html.unescape(str(value))).strip()


def extract_section_h2(arch: str, section_name: str) -> str | None:
    """Plain text of the first ``<h2>`` of the section that is not inside a
    nested section (tags stripped, entities unescaped, whitespace collapsed).
    ``None`` when the section has no such ``<h2>``. Raises
    :class:`SectionNotFound`."""
    section = _require_section(arch, section_name)
    span = _first_h2(section)
    if span is None:
        return None
    return normalize_text(_TAG_RE.sub("", arch[span[0]:span[1]]))


def replace_section_h2(arch: str, section_name: str, text: str) -> str:
    """Replace the inner text of the section's first (non nested) ``<h2>``
    with ``text`` (HTML-escaped). Everything else stays byte-identical."""
    section = _require_section(arch, section_name)
    span = _first_h2(section)
    if span is None:
        raise ArchError(f"section {section_name!r} has no <h2>")
    return arch[:span[0]] + html.escape(text, quote=False) + arch[span[1]:]


def extract_section_bg(arch: str, section_name: str) -> str | None:
    """URL of ``background-image: url(...)`` in the section's opening tag
    style, or ``None`` when absent. Raises :class:`SectionNotFound`."""
    section = _require_section(arch, section_name)
    style = _STYLE_RE.search(section.open_tag)
    if not style:
        return None
    bg = _BG_URL_RE.search(style.group(2))
    return bg.group(2).strip() if bg else None


def set_section_background(arch: str, section_name: str, url: str) -> str:
    """Set the section's background image URL. Only the opening tag changes.

    ``url`` must pass :func:`check_bg_url` (shape only; the caller checks the
    company). If the ``style`` attribute already declares ``background-image``
    (url or gradient) that declaration is replaced. Otherwise the standard
    cover declaration is prepended to the style (the attribute is created
    when missing).
    """
    error = check_bg_url(url)
    if error:
        raise ArchError(error)
    section = _require_section(arch, section_name)
    open_tag = section.open_tag
    declaration = f"background-image: url('{url}')"
    style = _STYLE_RE.search(open_tag)
    if style:
        value = style.group(2)
        if _BG_DECL_RE.search(value):
            new_value = _BG_DECL_RE.sub(lambda _m: declaration, value, count=1)
        else:
            new_value = BG_STYLE_PREFIX.format(url=url) + value
        new_open = open_tag[:style.start(2)] + new_value + open_tag[style.end(2):]
    else:
        attr = ' style="' + BG_STYLE_PREFIX.format(url=url).rstrip() + '"'
        head = open_tag[:-1]
        self_closing = head.endswith("/")
        if self_closing:
            head = head[:-1]
        new_open = head.rstrip() + attr + ("/>" if self_closing else ">")
    return arch[:section.start] + new_open + arch[section.open_end:]


def insert_sec1_after_hero(arch: str, text: str) -> str:
    """Insert the SEC1 skeleton right after the ``Hero`` section, using the
    Hero line's indentation. Raises :class:`ArchError` when SEC1 already
    exists and :class:`SectionNotFound` when there is no Hero."""
    if find_section(arch, "SEC1"):
        raise ArchError("section 'SEC1' already exists")
    hero = _require_section(arch, "Hero")
    line_start = arch.rfind("\n", 0, hero.start) + 1
    indent = arch[line_start:hero.start]
    if indent.strip():
        indent = ""
    skeleton = SEC1_SKELETON.replace("{TEXT}", html.escape(text, quote=False))
    block = "\n".join(indent + line for line in skeleton.split("\n"))
    return arch[:hero.end] + "\n" + block + arch[hero.end:]


# ---------------------------------------------------------------------------
# XML-RPC client
# ---------------------------------------------------------------------------

class OdooClient:
    """Minimal ``xmlrpc.client`` wrapper around ``/xmlrpc/2/common`` and
    ``/xmlrpc/2/object``. The password is kept in memory only and never
    logged."""

    def __init__(self, url: str, db: str, login: str, password: str, timeout: float = 300.0):
        self.url = url.rstrip("/")
        self.db = db
        self.login = login
        self._password = password
        socket.setdefaulttimeout(timeout)
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
        self._object = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)
        try:
            self.uid = self._common.authenticate(db, login, password, {})
        except (xmlrpc.client.Error, OSError) as exc:
            raise OdooError(f"cannot reach {self.url}: {exc}") from exc
        if not self.uid:
            raise OdooError(f"authentication failed for {login!r} on db {db!r}")

    def execute_kw(self, model: str, method: str, args: list, kwargs: dict | None = None):
        try:
            return self._object.execute_kw(
                self.db, self.uid, self._password, model, method, args, kwargs or {})
        except xmlrpc.client.Fault as exc:
            raise OdooError(f"{model}.{method}: {exc.faultString.strip().splitlines()[-1]}") from exc
        except (xmlrpc.client.Error, OSError) as exc:
            raise OdooError(f"{model}.{method}: {exc}") from exc

    def read(self, model: str, ids: list[int], fields: list[str], context: dict | None = None) -> list[dict]:
        kwargs = {"fields": fields}
        if context:
            kwargs["context"] = context
        return self.execute_kw(model, "read", [ids], kwargs)

    def read_one(self, model: str, res_id: int, fields: list[str], context: dict | None = None) -> dict:
        records = self.read(model, [res_id], fields, context)
        if not records:
            raise OdooError(f"{model} id {res_id} not found")
        return records[0]

    def search_read(self, model: str, domain: list, fields: list[str], context: dict | None = None,
                    limit: int | None = None) -> list[dict]:
        kwargs = {"fields": fields}
        if context:
            kwargs["context"] = context
        if limit:
            kwargs["limit"] = limit
        return self.execute_kw(model, "search_read", [domain], kwargs)

    def write(self, model: str, ids: list[int], values: dict, context: dict | None = None) -> bool:
        kwargs = {"context": context} if context else {}
        return self.execute_kw(model, "write", [ids, values], kwargs)

    # Convenience helpers -------------------------------------------------

    def language_codes(self, primary: str = DEFAULT_PRIMARY_LANG) -> list[str]:
        """Codes of the active languages, ``primary`` first (when active) and
        the rest sorted, so processing order is deterministic."""
        rows = self.search_read("res.lang", [("active", "=", True)], ["code"])
        return order_languages([row["code"] for row in rows], primary)

    def company_of_website(self, website_id: int) -> int:
        """Id of the company owning a website."""
        record = self.read_one("website", website_id, ["company_id"])
        company = record.get("company_id")
        if not company:
            raise OdooError(f"website {website_id} has no company")
        return int(company[0])

    def homepage_view_id(self, website_id: int) -> int | None:
        """Id of the view behind the website's ``/`` page, or ``None``."""
        rows = self.search_read(
            MODEL_PAGE, [("website_id", "=", int(website_id)), ("url", "=", "/")], ["view_id"], limit=1)
        if not rows:
            return None
        view = rows[0].get("view_id")
        if isinstance(view, (list, tuple)) and view:
            return int(view[0])
        return int(view) if view else None

    def read_arch(self, view_id: int, lang: str) -> str:
        record = self.read_one(MODEL_VIEW, view_id, [FIELD_ARCH], {"lang": lang})
        arch = record.get(FIELD_ARCH)
        if not isinstance(arch, str) or not arch:
            raise OdooError(f"view {view_id} has an empty arch for {lang}")
        return arch

    def write_arch(self, view_id: int, lang: str, arch: str) -> None:
        self.write(MODEL_VIEW, [view_id], {FIELD_ARCH: arch}, {"lang": lang})


def order_languages(codes: Iterable[str], primary: str) -> list[str]:
    """``primary`` first (when present) followed by the other codes sorted."""
    ordered = sorted(set(codes))
    if primary in ordered:
        ordered.remove(primary)
        ordered.insert(0, primary)
    return ordered


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    """Register ``--url/--db/--login`` on an argument parser.

    There is intentionally no ``--password`` flag: the password is read from
    ``ODOO_PASSWORD`` or prompted interactively (see :func:`resolve_password`)."""
    group = parser.add_argument_group("connection")
    group.add_argument("--url", default=DEFAULT_URL, help=f"Odoo base URL (default: {DEFAULT_URL})")
    group.add_argument("--db", default=DEFAULT_DB, help=f"database name (default: {DEFAULT_DB})")
    group.add_argument("--login", default=None, help="login; defaults to env ODOO_LOGIN")


def resolve_password(login: str, db: str) -> str:
    """Password from ``ODOO_PASSWORD``, else an interactive prompt when a TTY
    is available. Raises :class:`CredentialsError` otherwise."""
    password = os.environ.get("ODOO_PASSWORD")
    if password:
        return password
    if sys.stdin.isatty():
        password = getpass.getpass(f"Odoo password for {login} on db {db!r}: ")
        if password:
            return password
        raise CredentialsError("empty password")
    raise CredentialsError(
        "password required: set ODOO_PASSWORD (no TTY available to prompt for it)")


def client_from_args(args: argparse.Namespace) -> OdooClient:
    """Build an :class:`OdooClient` from CLI flags and environment."""
    login = args.login or os.environ.get("ODOO_LOGIN")
    if not login:
        raise CredentialsError("login required: pass --login or set ODOO_LOGIN")
    password = resolve_password(login, args.db)
    return OdooClient(args.url, args.db, login, password)


# ---------------------------------------------------------------------------
# Backup file (JSON lines)
# ---------------------------------------------------------------------------

EVENT_BACKUP = "backup"
EVENT_PENDING = "pending"
EVENT_APPLIED = "applied"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def backup_key(record: dict) -> tuple:
    """Identity of a written value: (model, res_id, field, lang)."""
    return (record["model"], int(record["res_id"]), record["field"], record.get("lang"))


class BackupWriter:
    """Append-only writer for ``backup.jsonl``.

    Three kinds of lines are written:

    * ``event="backup"``: the value present on the server before a write,
      with ``applied=false``. Written for every row of a batch and flushed
      before any write of that batch happens.
    * ``event="pending"``: appended and flushed immediately before the RPC
      write of that value is attempted. If the process dies between the
      write and the ``applied`` line, the pending line tells ``revertir.py``
      that the value may have changed.
    * ``event="applied"``: appended right after the corresponding write
      succeeded (same ``row_id``/``model``/``res_id``/``field``/``lang``,
      ``applied=true``). It carries no values.
    """

    def __init__(self, path: Path):
        self.path = Path(path)
        self._fh = None

    def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "a", encoding="utf-8")

    def close(self) -> None:
        if self._fh:
            self._fh.close()
            self._fh = None

    def _write(self, record: dict) -> None:
        if not self._fh:
            raise RuntimeError("backup file is not open")
        self._fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def flush(self) -> None:
        if self._fh:
            self._fh.flush()
            os.fsync(self._fh.fileno())

    def append_backup(self, *, site: int, campo: str, model: str, res_id: int, field: str,
                      lang: str | None, valor_anterior, valor_nuevo) -> None:
        self._write({
            "ts": utc_now_iso(),
            "event": EVENT_BACKUP,
            "row_id": f"{site}:{campo}",
            "site": site,
            "campo": campo,
            "model": model,
            "res_id": res_id,
            "field": field,
            "lang": lang,
            "valor_anterior": valor_anterior,
            "valor_nuevo": valor_nuevo,
            "applied": False,
        })

    def _append_event(self, event: str, *, site: int, campo: str, model: str, res_id: int,
                      field: str, lang: str | None) -> None:
        self._write({
            "ts": utc_now_iso(),
            "event": event,
            "row_id": f"{site}:{campo}",
            "site": site,
            "campo": campo,
            "model": model,
            "res_id": res_id,
            "field": field,
            "lang": lang,
            "applied": event == EVENT_APPLIED,
        })
        self.flush()

    def append_pending(self, **fields) -> None:
        """Flushed right before the RPC write is attempted."""
        self._append_event(EVENT_PENDING, **fields)

    def append_applied(self, **fields) -> None:
        """Flushed right after the RPC write succeeded."""
        self._append_event(EVENT_APPLIED, **fields)


def read_backup(path: Path) -> list[dict]:
    """Load every line of a backup file, in file order."""
    records = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path} line {number}: invalid JSON ({exc})") from exc
            record["_line"] = number
            records.append(record)
    return records


def truncate(value, width: int = 80) -> str:
    """Single-line, shortened representation for console output."""
    if value is None or value is False:
        return "<empty>"
    text = normalize_text(value) if isinstance(value, str) else str(value)
    if len(text) > width:
        return text[:width - 3] + "..."
    return text
