#!/usr/bin/env python3
"""Apply the proposals of ``cambios.csv`` to Odoo through XML-RPC.

Dry-run by default: current server values are read and compared with the
CSV, nothing is written. ``--apply`` performs the writes, site by site, in
batches. ``--offline`` validates and prints the plan from the CSV alone,
without connecting (checks that need the server are deferred).

Backup (``--backup``, default ``/home/odoo/Pending/jev-work/backup.jsonl``,
outside the git tree): before any write of a batch, the current value of
every affected record is appended as a ``backup`` line: one line per view
holding the full arch of EVERY language (active languages plus ``en_US``)
as a ``{lang: arch}`` dict, one line per company row (base64 for images). Immediately before each RPC write a
``pending`` line is flushed, and an ``applied`` line right after it succeeds,
so ``revertir.py`` can tell which values may have changed even if this
process dies mid-write.

Safety rules per row:

* rows below ``--min-confianza`` are skipped;
* view rows are only applied to the site's homepage view (``website.page``
  with ``url='/'``); any other view id fails the row;
* if the current server value differs from ``valor_anterior`` the row is
  skipped ("changed on server since analysis"). ``--force`` bypasses this
  check, is only accepted together with ``--only-site`` and only affects
  those sites;
* if the current value already equals ``valor_nuevo`` the row is skipped
  ("already applied");
* image files must live inside ``--zip-root``; background URLs must point at
  ``/web/image/res.company/<company of the site>/<microsite image field>``;
* a background row whose image upload failed in this run is failed too
  (never written pointing at a missing image);
* ``--apply`` against db ``prod`` asks for interactive confirmation unless
  ``--yes`` is given.

Languages: view rows (h2, bg, SEC1/Acerca insert, Acerca columns) are
transformed, checked and written in the primary language only
(``--primary-lang``, default ``es_ES``): one write per view with context
``{'lang': primary}``. ``ir.ui.view.arch_db`` is an xml_translate field, so
Odoo itself rebuilds every other language from that write (unchanged terms
keep their translation, new terms are copied in Spanish) and the
``website_auto_translate`` queue (enqueued on es_ES writes, processed by a
cron every 5 minutes) translates the new terms into the other languages.
Writing the other languages here would rebuild the rest again and mix
languages, so they are never written. Drift and "already applied" checks
look at the primary language only; the other languages are only read to be
backed up.

Legacy "Acerca" block: ``Acerca.col1``/``Acerca.col2`` set the full text
(and its 120 char preview) of a column, appending the column when it is
missing; ``Acerca.insert`` (JSON payload) inserts the whole two-column
section after SEC1 (or Hero). Within a site, inserts run first (SEC1 before
Acerca), then column, heading and background edits.

Multiple rows targeting the same view are combined in memory and written
once. Credentials: ``--login``/``ODOO_LOGIN`` and
``ODOO_PASSWORD`` (or an interactive prompt); there is no password flag.
"""
from __future__ import annotations

import argparse
import base64
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import jev_apply_lib as lib

STATUS_PLAN = "WOULD APPLY"
STATUS_APPLIED = "APPLIED"
STATUS_SKIP = "SKIP"
STATUS_FAIL = "FAIL"

REASON_ALREADY = "already applied"


@dataclass
class BackupEntry:
    """One ``backup`` line to write before the batch."""

    change: lib.Change
    model: str
    res_id: int
    field: str
    lang: str | None
    valor_anterior: object
    valor_nuevo: object


@dataclass
class WriteUnit:
    """One XML-RPC ``write`` call and the rows that depend on it.

    View units hold the original arch (``base``) and an ordered list of
    transformations so a row can be excluded at execution time (dependency
    failure) without discarding the other rows of the same view."""

    model: str
    res_id: int
    field: str
    lang: str | None                          # backup identity (None for views and company)
    value: object = None
    base: object = None
    ops: list = field(default_factory=list)   # [(Change, callable(arch) -> arch)]
    changes: list = field(default_factory=list)
    write_lang: str | None = None             # context lang of the write (views: primary)
    archs: dict = field(default_factory=dict)  # views: {lang: arch} of every language, for the backup
    done: bool = False
    error: str = ""

    @property
    def key(self) -> tuple:
        return (self.model, self.res_id, self.field, self.lang)

    @property
    def dep_key(self) -> tuple:
        return (self.model, self.res_id, self.field)

    def build(self, excluded: set[int]) -> object:
        """Value to write, leaving out the transformations of ``excluded``
        changes (by ``id``)."""
        if not self.ops:
            return self.value
        arch = self.base
        for change, op in self.ops:
            if id(change) in excluded:
                continue
            arch = op(arch)
        return arch


@dataclass
class Outcome:
    """Decision for one CSV row."""

    change: lib.Change
    status: str
    reason: str = ""
    current: str = ""


class SiteContext:
    """Working state while preparing one site of a batch."""

    def __init__(self, client, site: int, company_id: int, langs: list[str], args, rows):
        self.client = client
        self.site = site
        self.company_id = company_id
        self.langs = langs
        self.args = args
        self.rows = rows
        self.primary_lang = langs[0]
        self.backup_langs = lib.backup_languages(langs)
        # Primary language arch per view: as read, and with the staged edits.
        self._arch_original: dict[int, str] = {}
        self._arch_work: dict[int, str] = {}
        self._arch_all: dict[int, dict[str, str]] = {}
        self._company_values: dict[str, object] = {}
        self.units: dict[tuple, WriteUnit] = {}
        self.backup_entries: list[BackupEntry] = []
        self.outcomes: list[Outcome] = []
        # id(change) -> (model, res_id, field) the row's write depends on.
        self.dependencies: dict[int, tuple] = {}

    @property
    def forced(self) -> bool:
        """``--force`` only bypasses the drift check for ``--only-site`` sites."""
        return bool(self.args.force) and self.site in (self.args.only_site or ())

    # Reads (cached per site) ------------------------------------------------

    def original_arch(self, view_id: int) -> str:
        """Primary language arch as read from the server."""
        if view_id not in self._arch_original:
            arch = self.client.read_arch(view_id, self.primary_lang)
            self._arch_original[view_id] = arch
            self._arch_work.setdefault(view_id, arch)
        return self._arch_original[view_id]

    def work_arch(self, view_id: int) -> str:
        """Primary language arch with the edits staged so far."""
        self.original_arch(view_id)
        return self._arch_work[view_id]

    def all_archs(self, view_id: int) -> dict[str, str]:
        """``{lang: arch}`` of every backed-up language, read before any
        write (Odoo rewrites all of them when the primary is written)."""
        if view_id not in self._arch_all:
            archs = {}
            for lang in self.backup_langs:
                archs[lang] = self.original_arch(view_id) if lang == self.primary_lang \
                    else self.client.read_arch(view_id, lang)
            self._arch_all[view_id] = archs
        return self._arch_all[view_id]

    def company_value(self, field_name: str):
        if field_name not in self._company_values:
            record = self.client.read_one(lib.MODEL_COMPANY, self.company_id, [field_name])
            self._company_values[field_name] = record.get(field_name)
        return self._company_values[field_name]

    # Pending writes -----------------------------------------------------------

    def stage_arch(self, change: lib.Change, view_id: int, op: Callable[[str], str]) -> None:
        """Apply ``op`` to the primary language working arch of the view and
        record the transformation on the view's single write unit. The
        first row of a view also reads every language for the backup."""
        key = (lib.MODEL_VIEW, view_id, lib.FIELD_ARCH, None)
        unit = self.units.get(key)
        if unit is None:
            archs = self.all_archs(view_id)   # may raise: nothing staged yet
            unit = self.units[key] = WriteUnit(
                lib.MODEL_VIEW, view_id, lib.FIELD_ARCH, None, base=self.original_arch(view_id),
                write_lang=self.primary_lang, archs=archs)
        self._arch_work[view_id] = op(self.work_arch(view_id))
        unit.ops.append((change, op))
        if change not in unit.changes:
            unit.changes.append(change)

    def stage_company(self, change: lib.Change, field_name: str, previous, value, backup_new) -> None:
        self.backup_entries.append(BackupEntry(
            change, lib.MODEL_COMPANY, self.company_id, field_name, None, previous, backup_new))
        key = (lib.MODEL_COMPANY, self.company_id, field_name, None)
        unit = self.units[key] = WriteUnit(lib.MODEL_COMPANY, self.company_id, field_name, None, value=value)
        unit.changes.append(change)
        self._company_values[field_name] = value

    def outcome_for(self, change: lib.Change) -> Outcome | None:
        for outcome in self.outcomes:
            if outcome.change is change:
                return outcome
        return None


# ---------------------------------------------------------------------------
# Row preparation
# ---------------------------------------------------------------------------

def _drift_reason(change: lib.Change) -> str:
    return f"changed on server since analysis (csv_prev={lib.truncate(change.valor_anterior)!r})"


def _changed_on_server(ctx: SiteContext, change: lib.Change, current) -> Outcome | None:
    """Return a SKIP outcome when the server value no longer matches the CSV."""
    if ctx.forced:
        return None
    if lib.normalize_text(current) != lib.normalize_text(change.valor_anterior):
        return Outcome(change, STATUS_SKIP, _drift_reason(change), lib.truncate(current))
    return None


def prepare_company_field(ctx: SiteContext, change: lib.Change) -> Outcome:
    field_name = change.target.field
    raw = ctx.company_value(field_name)
    if field_name == "category_id":
        current = str(raw[0]) if isinstance(raw, (list, tuple)) and raw else ""
        new_text = change.valor_nuevo.strip()
        if new_text and not new_text.isdigit():
            return Outcome(change, STATUS_FAIL, f"category_id must be an integer id, got {new_text!r}", current)
        value = int(new_text) if new_text else False
        previous = int(raw[0]) if current else None
        display = f"{current} ({raw[1]})" if current else ""
    else:
        current = raw if isinstance(raw, str) else ""
        value = change.valor_nuevo if change.valor_nuevo else False
        previous = current or None
        display = current
    if lib.normalize_text(current) == lib.normalize_text(change.valor_nuevo):
        return Outcome(change, STATUS_SKIP, REASON_ALREADY, lib.truncate(display))
    skip = _changed_on_server(ctx, change, current)
    if skip:
        return skip
    ctx.stage_company(change, field_name, previous, value, change.valor_nuevo)
    return Outcome(change, STATUS_PLAN, "", lib.truncate(display))


def prepare_company_image(ctx: SiteContext, change: lib.Change) -> Outcome:
    field_name = change.target.field
    try:
        path = lib.zip_image_path(ctx.args.zip_root, change.valor_nuevo)
    except ValueError as exc:
        return Outcome(change, STATUS_FAIL, str(exc))
    if not path.is_file():
        return Outcome(change, STATUS_FAIL, f"image file not found: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    raw = ctx.company_value(field_name)
    current = raw if isinstance(raw, str) else ""
    current_display = f"<{len(current)} b64 chars>" if current else ""
    if current == encoded:
        return Outcome(change, STATUS_SKIP, REASON_ALREADY, current_display)
    if not ctx.forced:
        # The CSV cannot carry base64, so valor_anterior only says whether
        # the field was empty at analysis time.
        expected_empty = not change.valor_anterior.strip()
        if expected_empty and current:
            return Outcome(change, STATUS_SKIP, _drift_reason(change), current_display)
        if not expected_empty and not current:
            return Outcome(change, STATUS_SKIP, _drift_reason(change), current_display)
    ctx.stage_company(change, field_name, current or None, encoded, change.valor_nuevo)
    return Outcome(change, STATUS_PLAN, f"{path.stat().st_size} bytes from {path.name}", current_display)


def _decide(ctx: SiteContext, change: lib.Change, current, done: bool) -> Outcome | None:
    """SKIP when the primary language already holds the new value or no
    longer matches ``valor_anterior``; ``None`` when the row can be staged."""
    if done:
        return Outcome(change, STATUS_SKIP, REASON_ALREADY, lib.truncate(current))
    return _changed_on_server(ctx, change, current)


def _section_missing(ctx: SiteContext, view_id: int, section: str) -> str | None:
    return None if lib.find_section(ctx.work_arch(view_id), section) else \
        f"section {section!r} not found in view {view_id} ({ctx.primary_lang})"


def prepare_view_h2(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id, section = change.target.view_id, change.target.section
    text = change.valor_nuevo
    missing = _section_missing(ctx, view_id, section)
    if missing:
        return Outcome(change, STATUS_FAIL, missing)
    current = lib.extract_section_h2(ctx.work_arch(view_id), section)
    skip = _decide(ctx, change, current, lib.normalize_text(current) == lib.normalize_text(text))
    if skip:
        return skip
    ctx.stage_arch(change, view_id, lambda arch, s=section, t=text: lib.replace_section_h2(arch, s, t))
    return Outcome(change, STATUS_PLAN, "", lib.truncate(current))


def _sibling_image_row(ctx: SiteContext, image_field: str, path: str | None) -> lib.Change | None:
    for row in ctx.rows:
        if row.target.kind == lib.KIND_COMPANY_IMAGE and row.target.field == image_field \
                and (path is None or row.valor_nuevo.strip() == path):
            return row
    return None


def _resolve_bg_url(ctx: SiteContext, change: lib.Change) -> tuple[str | None, str]:
    """Return (url, error). Zip paths must be uploaded by a sibling row; URLs
    must belong to the site's company. Registers the dependency on the
    uploading row when that row is going to be written in this run."""
    value = change.valor_nuevo.strip()
    section = change.target.section
    if value.startswith("/"):
        error = lib.check_bg_url(value, ctx.company_id)
        if error:
            return None, error
        url, image_field = value, lib.bg_url_field(value)
        uploader = _sibling_image_row(ctx, image_field, None)
    else:
        image_field = lib.SECTION_IMAGE_FIELD.get(section)
        if not image_field:
            return None, f"no res.company image field is mapped to section {section!r}"
        uploader = _sibling_image_row(ctx, image_field, value)
        if uploader is None:
            return None, f"no res_company.{image_field} row of site {ctx.site} uploads {value!r}"
        url = lib.company_image_url(ctx.company_id, image_field)
    if uploader is not None:
        outcome = ctx.outcome_for(uploader)
        if outcome is None or outcome.status == STATUS_FAIL:
            return None, f"depends on failed row res_company.{image_field}"
        if outcome.status == STATUS_SKIP and outcome.reason != REASON_ALREADY:
            return None, f"depends on skipped row res_company.{image_field} ({outcome.reason})"
        if outcome.status == STATUS_PLAN:
            ctx.dependencies[id(change)] = (lib.MODEL_COMPANY, ctx.company_id, image_field)
    return url, ""


def prepare_view_bg(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id, section = change.target.view_id, change.target.section
    url, error = _resolve_bg_url(ctx, change)
    if error:
        return Outcome(change, STATUS_FAIL, error)
    missing = _section_missing(ctx, view_id, section)
    if missing:
        return Outcome(change, STATUS_FAIL, missing)
    current = lib.extract_section_bg(ctx.work_arch(view_id), section)
    skip = _decide(ctx, change, current, current == url)
    if skip:
        return skip
    ctx.stage_arch(change, view_id, lambda arch, s=section, u=url: lib.set_section_background(arch, s, u))
    return Outcome(change, STATUS_PLAN, f"url={url}", lib.truncate(current))


def _dry_run_op(ctx: SiteContext, view_id: int, op: Callable[[str], str]) -> str:
    """Run ``op`` on the working arch without staging. Returns the error
    message or ``""``."""
    try:
        op(ctx.work_arch(view_id))
    except lib.ArchError as exc:
        return f"{type(exc).__name__} ({ctx.primary_lang}): {exc}"
    return ""


def prepare_view_column(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id, section, n = change.target.view_id, change.target.section, change.target.column
    text = change.valor_nuevo
    if not text.strip():
        return Outcome(change, STATUS_FAIL, f"empty text for {section}.col{n}")
    missing = _section_missing(ctx, view_id, section)
    if missing:
        return Outcome(change, STATUS_FAIL, missing)
    arch = ctx.work_arch(view_id)
    current = lib.extract_acerca_column(arch, n)
    if lib.normalize_text(current) == lib.normalize_text(text):
        return Outcome(change, STATUS_SKIP, REASON_ALREADY, lib.truncate(current))
    # When the section is created by an Acerca.insert row of this run, the
    # server had no column at analysis time: drift is checked against "".
    baseline = current if lib.find_section(ctx.original_arch(view_id), section) else ""
    skip = _changed_on_server(ctx, change, baseline)
    if skip:
        skip.current = lib.truncate(current)
        return skip
    note = f"column {n} appended" if n not in lib.acerca_column_slots(arch) else ""
    op = lambda arch, c=n, t=text, s=ctx.site: lib.set_acerca_column(arch, c, t, s)  # noqa: E731
    error = _dry_run_op(ctx, view_id, op)
    if error:
        return Outcome(change, STATUS_FAIL, error, lib.truncate(current))
    ctx.stage_arch(change, view_id, op)
    return Outcome(change, STATUS_PLAN, note, lib.truncate(current))


def prepare_acerca_insert(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id = change.target.view_id
    try:
        payload = lib.parse_acerca_payload(change.valor_nuevo)
    except ValueError as exc:
        return Outcome(change, STATUS_FAIL, str(exc))
    current = lib.extract_acerca_section(ctx.work_arch(view_id))
    skip = _decide(ctx, change, current, current == lib.acerca_payload_key(payload))
    if skip:
        return skip
    if current:
        return Outcome(change, STATUS_FAIL,
                       f"section 'Acerca' already exists with other content in {ctx.primary_lang}",
                       lib.truncate(current))
    op = lambda arch, p=payload: lib.insert_acerca_section(arch, p)  # noqa: E731
    error = _dry_run_op(ctx, view_id, op)
    if error:
        return Outcome(change, STATUS_FAIL, error)
    ctx.stage_arch(change, view_id, op)
    return Outcome(change, STATUS_PLAN, "", lib.truncate(current))


def prepare_view_insert(ctx: SiteContext, change: lib.Change) -> Outcome:
    if change.target.section == lib.ACERCA_SECTION:
        return prepare_acerca_insert(ctx, change)
    view_id = change.target.view_id
    text = change.valor_nuevo
    exists = lib.find_section(ctx.work_arch(view_id), "SEC1") is not None
    current = lib.extract_section_h2(ctx.work_arch(view_id), "SEC1") if exists else None
    skip = _decide(ctx, change, current, exists and lib.normalize_text(current) == lib.normalize_text(text))
    if skip:
        return skip
    if exists:
        op = lambda arch, t=text: lib.replace_section_h2(arch, "SEC1", t)  # noqa: E731
    else:
        op = lambda arch, t=text: lib.insert_sec1_after_hero(arch, t)  # noqa: E731
    error = _dry_run_op(ctx, view_id, op)
    if error:
        return Outcome(change, STATUS_FAIL, error)
    ctx.stage_arch(change, view_id, op)
    return Outcome(change, STATUS_PLAN, "", lib.truncate(current))


PREPARERS = {
    lib.KIND_COMPANY_FIELD: prepare_company_field,
    lib.KIND_COMPANY_IMAGE: prepare_company_image,
    lib.KIND_VIEW_H2: prepare_view_h2,
    lib.KIND_VIEW_BG: prepare_view_bg,
    lib.KIND_VIEW_INSERT: prepare_view_insert,
    lib.KIND_VIEW_COLUMN: prepare_view_column,
}


def prepare_site(client, site: int, rows: list[lib.Change], langs: list[str], args) -> SiteContext | list[Outcome]:
    """Read current values and decide every row of one site.

    Returns the :class:`SiteContext` or, when the site itself cannot be
    resolved, a list of FAIL outcomes."""
    try:
        company_id = client.company_of_website(site)
        homepage_view = client.homepage_view_id(site)
    except lib.OdooError as exc:
        return [Outcome(row, STATUS_FAIL, f"cannot resolve site: {exc}") for row in rows]
    ctx = SiteContext(client, site, company_id, langs, args, rows)
    for change in rows:
        target = change.target
        if target.model == lib.MODEL_VIEW:
            if homepage_view is None:
                ctx.outcomes.append(Outcome(change, STATUS_FAIL,
                                            f"site {site} has no homepage page (website.page url='/')"))
                continue
            if target.view_id != homepage_view:
                ctx.outcomes.append(Outcome(change, STATUS_FAIL,
                                            f"view {target.view_id} is not the homepage view of site {site} "
                                            f"(homepage view is {homepage_view})"))
                continue
        try:
            outcome = PREPARERS[target.kind](ctx, change)
        except (lib.OdooError, lib.ArchError, OSError, ValueError) as exc:
            outcome = Outcome(change, STATUS_FAIL, f"{type(exc).__name__}: {exc}")
        ctx.outcomes.append(outcome)
    return ctx


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def write_backup(backup: lib.BackupWriter, contexts: list[SiteContext]) -> None:
    """Company rows get one line each; every view gets one line with the
    arch of all its languages."""
    for ctx in contexts:
        for entry in ctx.backup_entries:
            backup.append_backup(
                site=ctx.site, campo=entry.change.campo, model=entry.model, res_id=entry.res_id,
                field=entry.field, lang=entry.lang, valor_anterior=entry.valor_anterior,
                valor_nuevo=entry.valor_nuevo)
        for unit in ctx.units.values():
            if unit.model != lib.MODEL_VIEW:
                continue
            rows = [{"campo": c.campo, "valor_anterior": c.valor_anterior, "valor_nuevo": c.valor_nuevo}
                    for c in unit.changes]
            backup.append_view_backup(site=ctx.site, rows=rows, res_id=unit.res_id, archs=unit.archs,
                                      primary_lang=ctx.primary_lang)
    backup.flush()


def _event_fields(ctx: SiteContext, unit: WriteUnit, change: lib.Change) -> dict:
    return dict(site=ctx.site, campo=change.campo, model=unit.model, res_id=unit.res_id,
                field=unit.field, lang=unit.lang)


def execute_site(ctx: SiteContext, backup: lib.BackupWriter, stop_on_error: bool) -> bool:
    """Perform the staged writes of one site. Returns False on an error when
    ``stop_on_error`` is set.

    Units are executed in staging order (company writes first). A view row
    whose dependency (a ``res.company`` image write) failed is excluded from
    its unit and failed, so no background is written pointing at a missing
    image."""
    failed_deps: set[tuple] = set()
    for unit in ctx.units.values():
        excluded: set[int] = set()
        for change in unit.changes:
            dep = ctx.dependencies.get(id(change))
            if dep is not None and dep in failed_deps:
                excluded.add(id(change))
                outcome = ctx.outcome_for(change)
                if outcome is not None and outcome.status == STATUS_PLAN:
                    outcome.status = STATUS_FAIL
                    outcome.reason = f"not written: depends on failed write {dep[0]}[{dep[1]}].{dep[2]}"
        active = [c for c in unit.changes if id(c) not in excluded]
        if not active:
            unit.error = "all rows of this write depend on failed writes"
            continue
        try:
            value = unit.build(excluded)
        except lib.ArchError as exc:
            unit.error = f"{type(exc).__name__}: {exc}"
            failed_deps.add(unit.dep_key)
            print(f"  ERROR building {unit.model}[{unit.res_id}].{unit.field} lang={unit.write_lang}: {exc}")
            if stop_on_error:
                _finalize_outcomes(ctx)
                return False
            continue
        context = {"lang": unit.write_lang} if unit.write_lang else None
        for change in active:
            backup.append_pending(**_event_fields(ctx, unit, change))
        try:
            ctx.client.write(unit.model, [unit.res_id], {unit.field: value}, context)
            unit.done = True
        except lib.OdooError as exc:
            unit.error = str(exc)
            failed_deps.add(unit.dep_key)
            print(f"  ERROR writing {unit.model}[{unit.res_id}].{unit.field} lang={unit.write_lang}: {exc}")
            if stop_on_error:
                _finalize_outcomes(ctx)
                return False
            continue
        for change in active:
            backup.append_applied(**_event_fields(ctx, unit, change))
    _finalize_outcomes(ctx)
    return True


def _finalize_outcomes(ctx: SiteContext) -> None:
    """Turn WOULD APPLY into APPLIED or FAIL according to the write units."""
    for outcome in ctx.outcomes:
        if outcome.status != STATUS_PLAN:
            continue
        units = [u for u in ctx.units.values() if outcome.change in u.changes]
        errors = [u.error for u in units if u.error]
        if errors:
            outcome.status, outcome.reason = STATUS_FAIL, errors[0]
        elif all(u.done for u in units):
            outcome.status = STATUS_APPLIED
        else:
            outcome.status, outcome.reason = STATUS_FAIL, "not written (stopped)"


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_outcome(outcome: Outcome) -> None:
    change = outcome.change
    parts = [f"  {change.campo:<45} {outcome.status:<12}"]
    if outcome.current or outcome.status in (STATUS_PLAN, STATUS_APPLIED, STATUS_SKIP):
        parts.append(f"current={outcome.current or '<empty>'!r}")
    if outcome.status in (STATUS_PLAN, STATUS_APPLIED):
        parts.append(f"csv_prev={lib.truncate(change.valor_anterior)!r}")
        parts.append(f"new={lib.truncate(change.valor_nuevo)!r}")
    if outcome.reason:
        parts.append(outcome.reason)
    print(" | ".join(parts))


def print_summary(outcomes: list[Outcome], apply: bool, backup_path: Path | None,
                  extra_failed: int = 0) -> None:
    counts = {STATUS_APPLIED: 0, STATUS_PLAN: 0, STATUS_SKIP: 0, STATUS_FAIL: 0}
    for outcome in outcomes:
        counts[outcome.status] = counts.get(outcome.status, 0) + 1
    print()
    print("Summary:")
    if apply:
        print(f"  applied: {counts[STATUS_APPLIED]}")
    else:
        print(f"  would apply: {counts[STATUS_PLAN]}")
    print(f"  skipped: {counts[STATUS_SKIP]}")
    print(f"  failed:  {counts[STATUS_FAIL] + extra_failed}")
    if backup_path:
        print(f"  backup:  {backup_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Apply cambios.csv to Odoo through XML-RPC (dry-run by default).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    lib.add_connection_args(parser)
    parser.add_argument("--csv", type=Path, default=lib.DEFAULT_CSV, help="proposals file")
    parser.add_argument("--zip-root", type=Path, default=lib.DEFAULT_ZIP_ROOT,
                        help="root directory that image paths are relative to")
    parser.add_argument("--backup", type=Path, default=lib.DEFAULT_BACKUP,
                        help="backup JSON lines file (kept outside the git tree)")
    parser.add_argument("--apply", action="store_true", help="perform the writes (default: dry-run)")
    parser.add_argument("--offline", action="store_true",
                        help="validate and print the plan from the CSV alone, without connecting")
    parser.add_argument("--yes", action="store_true",
                        help="skip the interactive confirmation when applying to db 'prod'")
    parser.add_argument("--batch-size", type=int, default=10, help="sites per batch")
    parser.add_argument("--only-site", type=lib.parse_site_list, default=None,
                        help="comma separated website ids to process")
    parser.add_argument("--min-confianza", type=float, default=0.85,
                        help="rows with a lower confianza are skipped")
    parser.add_argument("--from-batch", type=int, default=1, help="resume from this batch number (1-based)")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="abort on the first failed write instead of continuing")
    parser.add_argument("--force", action="store_true",
                        help="write even if the server value differs from valor_anterior; "
                             "requires --only-site and only affects those sites")
    parser.add_argument("--primary-lang", default=lib.DEFAULT_PRIMARY_LANG,
                        help="only language written for views (the others are regenerated by Odoo "
                             "and translated by website_auto_translate); also used for the drift check")
    return parser


def validate_args(parser: argparse.ArgumentParser, args) -> None:
    if args.batch_size < 1 or args.from_batch < 1:
        parser.error("--batch-size and --from-batch must be >= 1")
    if args.force and not args.only_site:
        parser.error("--force requires --only-site (it is scoped to those sites)")
    if args.offline and args.apply:
        parser.error("--offline cannot be combined with --apply")


def confirm_prod(args) -> bool:
    """Interactive guard for ``--apply`` on db ``prod``."""
    if not args.apply or args.db != "prod" or args.yes:
        return True
    if not sys.stdin.isatty():
        print("refusing to --apply on db 'prod' without confirmation: pass --yes or run interactively",
              file=sys.stderr)
        return False
    try:
        answer = input("You are about to WRITE to db 'prod'. Type 'prod' to continue: ")
    except EOFError:
        answer = ""
    if answer.strip() != "prod":
        print("aborted: confirmation not given", file=sys.stderr)
        return False
    return True


def select_changes(changes: list[lib.Change], args) -> tuple[list[lib.Change], list[Outcome]]:
    """Apply --only-site, duplicate detection and --min-confianza.

    Returns (kept, outcomes of skipped/failed rows)."""
    kept, outcomes = [], []
    counts: dict[tuple[int, str], int] = {}
    for change in changes:
        counts[(change.site, change.campo)] = counts.get((change.site, change.campo), 0) + 1
    for change in changes:
        if args.only_site is not None and change.site not in args.only_site:
            continue
        if counts[(change.site, change.campo)] > 1:
            outcomes.append(Outcome(change, STATUS_FAIL, "duplicated (site, campo) row in the CSV"))
            continue
        if change.confianza < args.min_confianza:
            outcomes.append(Outcome(change, STATUS_SKIP,
                                    f"confianza {change.confianza:.2f} < {args.min_confianza:.2f}"))
            continue
        kept.append(change)
    return kept, outcomes


def validate_offline(change: lib.Change, rows: list[lib.Change], zip_root: Path) -> str:
    """Checks that do not need the server. Returns an error message or ``""``."""
    target = change.target
    if target.kind == lib.KIND_COMPANY_IMAGE:
        try:
            path = lib.zip_image_path(zip_root, change.valor_nuevo)
        except ValueError as exc:
            return str(exc)
        if not path.is_file():
            return f"image file not found: {path}"
    elif target.section == lib.ACERCA_SECTION and target.model == lib.MODEL_VIEW:
        op = f"col{target.column}" if target.kind == lib.KIND_VIEW_COLUMN else \
            {lib.KIND_VIEW_INSERT: "insert", lib.KIND_VIEW_H2: "h2", lib.KIND_VIEW_BG: "bg"}[target.kind]
        if op not in lib.ACERCA_OPS:
            return f"unsupported op {op!r} for section 'Acerca' (supported: {', '.join(lib.ACERCA_OPS)})"
        if target.kind == lib.KIND_VIEW_INSERT:
            try:
                lib.parse_acerca_payload(change.valor_nuevo)
            except ValueError as exc:
                return str(exc)
        elif not change.valor_nuevo.strip():
            return f"empty text for Acerca.{op}"
    elif target.kind == lib.KIND_COMPANY_FIELD and target.field == "category_id":
        new_text = change.valor_nuevo.strip()
        if new_text and not new_text.isdigit():
            return f"category_id must be an integer id, got {new_text!r}"
    elif target.kind == lib.KIND_VIEW_BG:
        value = change.valor_nuevo.strip()
        if value.startswith("/"):
            return lib.check_bg_url(value, None)
        image_field = lib.SECTION_IMAGE_FIELD.get(target.section)
        if not image_field:
            return f"no res.company image field is mapped to section {target.section!r}"
        uploader = next((r for r in rows if r.target.kind == lib.KIND_COMPANY_IMAGE
                         and r.target.field == image_field and r.valor_nuevo.strip() == value), None)
        if uploader is None:
            return f"no res_company.{image_field} row of site {change.site} uploads {value!r}"
        try:
            path = lib.zip_image_path(zip_root, value)
        except ValueError as exc:
            return str(exc)
        if not path.is_file():
            return f"image file not found: {path}"
    return ""


def run_offline(grouped: dict[int, list[lib.Change]], args) -> list[Outcome]:
    print("offline: view ownership and 'changed on server' checks are deferred to the connected run")
    outcomes: list[Outcome] = []
    site_batches = list(lib.batches(list(grouped), args.batch_size))
    for number, sites in enumerate(site_batches, start=1):
        print(f"[batch {number}/{len(site_batches)}] sites {', '.join(map(str, sites))}")
        for site in sites:
            print(f" site {site}")
            for change in grouped[site]:
                error = validate_offline(change, grouped[site], args.zip_root)
                outcome = Outcome(change, STATUS_FAIL if error else STATUS_PLAN, error)
                outcomes.append(outcome)
                status = "FAIL" if error else "PLAN"
                line = (f"  {change.campo:<45} {status:<12} | csv_prev={lib.truncate(change.valor_anterior)!r}"
                        f" | new={lib.truncate(change.valor_nuevo)!r} | confianza={change.confianza:.2f}")
                print(line + (f" | {error}" if error else ""))
    return outcomes


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    try:
        changes, invalid = lib.load_changes(args.csv)
    except (OSError, ValueError) as exc:
        print(f"cannot load {args.csv}: {exc}", file=sys.stderr)
        return 2
    for row in invalid:
        print(f"  csv row {row.line} site {row.site!r} {row.campo!r}: FAIL | {row.error}")
    kept, outcomes = select_changes(changes, args)
    for outcome in outcomes:
        print(f"  site {outcome.change.site} {outcome.change.campo}: {outcome.status} | {outcome.reason}")
    grouped = lib.group_by_site(kept)
    print(f"{len(kept)} row(s) across {len(grouped)} site(s); {len(outcomes)} skipped/failed before "
          f"processing; {len(invalid)} unparsable row(s)")

    if args.offline:
        outcomes.extend(run_offline(grouped, args))
        print_summary(outcomes, apply=False, backup_path=None, extra_failed=len(invalid))
        failed = invalid or any(o.status == STATUS_FAIL for o in outcomes)
        return 1 if failed else 0

    if not confirm_prod(args):
        return 2
    try:
        client = lib.client_from_args(args)
    except lib.OdooError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    langs = client.language_codes(args.primary_lang)
    if not langs:
        print("no active languages found", file=sys.stderr)
        return 2
    if langs[0] != args.primary_lang:
        print(f"primary language {args.primary_lang!r} is not active (active: {', '.join(langs)})",
              file=sys.stderr)
        return 2
    print(f"connected to {args.url} db={args.db} uid={client.uid}; languages: {', '.join(langs)} "
          f"(views written in {args.primary_lang} only)")
    mode = "APPLY" if args.apply else "DRY-RUN"

    backup = lib.BackupWriter(args.backup)
    if args.apply:
        backup.open()

    stopped = False
    site_batches = list(lib.batches(list(grouped), args.batch_size))
    try:
        for number, sites in enumerate(site_batches, start=1):
            if number < args.from_batch:
                continue
            print(f"\n[{mode} batch {number}/{len(site_batches)}] sites {', '.join(map(str, sites))}")
            contexts: list[SiteContext] = []
            for site in sites:
                prepared = prepare_site(client, site, grouped[site], langs, args)
                if isinstance(prepared, list):
                    outcomes.extend(prepared)
                    print(f" site {site}")
                    for outcome in prepared:
                        print_outcome(outcome)
                    if args.stop_on_error:
                        stopped = True
                        break
                    continue
                contexts.append(prepared)
                forced = " FORCED" if prepared.forced else ""
                print(f" site {site} (company {prepared.company_id}, primary lang {prepared.primary_lang}{forced})")
                for outcome in prepared.outcomes:
                    print_outcome(outcome)
                if args.stop_on_error and any(o.status == STATUS_FAIL for o in prepared.outcomes):
                    stopped = True
                    break
            if not args.apply or stopped:
                for ctx in contexts:
                    if args.apply:
                        _finalize_outcomes(ctx)
                    outcomes.extend(ctx.outcomes)
                if stopped:
                    break
                continue
            write_backup(backup, contexts)
            for ctx in contexts:
                ok = execute_site(ctx, backup, args.stop_on_error)
                outcomes.extend(ctx.outcomes)
                for outcome in ctx.outcomes:
                    if outcome.status in (STATUS_APPLIED, STATUS_FAIL):
                        print_outcome(outcome)
                if not ok:
                    stopped = True
                    break
            if stopped:
                break
    finally:
        backup.close()

    print_summary(outcomes, apply=args.apply, backup_path=args.backup if args.apply else None,
                  extra_failed=len(invalid))
    if stopped:
        print("stopped on error (--stop-on-error)")
    failed = bool(invalid) or any(o.status == STATUS_FAIL for o in outcomes)
    return 1 if failed or stopped else 0


if __name__ == "__main__":
    sys.exit(main())
