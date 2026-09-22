#!/usr/bin/env python3
"""Apply the proposals of ``cambios.csv`` to Odoo through XML-RPC.

Dry-run by default: current server values are read and compared with the
CSV, nothing is written. ``--apply`` performs the writes, site by site, in
batches. Before any write of a batch, the current value of every affected
record (full arch per language for views, base64 for images) is appended to
``backup.jsonl`` so ``revertir.py`` can restore it.

Safety rules per row:

* rows below ``--min-confianza`` are skipped;
* if the current server value differs from ``valor_anterior`` the row is
  skipped ("changed on server since analysis") unless ``--force``;
* if the current value already equals ``valor_nuevo`` the row is skipped
  ("already applied").

Views are edited for every active language. Multiple rows targeting the same
view are combined in memory and written once per language.
"""
from __future__ import annotations

import argparse
import base64
import sys
from dataclasses import dataclass, field
from pathlib import Path

import jev_apply_lib as lib

STATUS_PLAN = "WOULD APPLY"
STATUS_APPLIED = "APPLIED"
STATUS_SKIP = "SKIP"
STATUS_FAIL = "FAIL"


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
    """One XML-RPC ``write`` call and the rows that depend on it."""

    model: str
    res_id: int
    field: str
    lang: str | None
    value: object
    changes: list = field(default_factory=list)
    done: bool = False
    error: str = ""

    @property
    def key(self) -> tuple:
        return (self.model, self.res_id, self.field, self.lang)


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
        self.primary_lang = args.primary_lang if args.primary_lang in langs else langs[0]
        self._arch_original: dict[tuple[int, str], str] = {}
        self._arch_work: dict[tuple[int, str], str] = {}
        self._company_values: dict[str, object] = {}
        self.units: dict[tuple, WriteUnit] = {}
        self.backup_entries: list[BackupEntry] = []
        self.outcomes: list[Outcome] = []

    # Reads (cached per site) ------------------------------------------------

    def original_arch(self, view_id: int, lang: str) -> str:
        key = (view_id, lang)
        if key not in self._arch_original:
            arch = self.client.read_arch(view_id, lang)
            self._arch_original[key] = arch
            self._arch_work.setdefault(key, arch)
        return self._arch_original[key]

    def work_arch(self, view_id: int, lang: str) -> str:
        self.original_arch(view_id, lang)
        return self._arch_work[(view_id, lang)]

    def company_value(self, field_name: str):
        if field_name not in self._company_values:
            record = self.client.read_one(lib.MODEL_COMPANY, self.company_id, [field_name])
            self._company_values[field_name] = record.get(field_name)
        return self._company_values[field_name]

    # Pending writes -----------------------------------------------------------

    def stage_arch(self, change: lib.Change, view_id: int, lang: str, new_arch: str) -> None:
        """Record a transformed arch for (view, lang) and its backup entry."""
        previous = self.work_arch(view_id, lang)
        self._arch_work[(view_id, lang)] = new_arch
        self.backup_entries.append(BackupEntry(
            change, lib.MODEL_VIEW, view_id, lib.FIELD_ARCH, lang, previous, change.valor_nuevo))
        key = (lib.MODEL_VIEW, view_id, lib.FIELD_ARCH, lang)
        unit = self.units.get(key)
        if unit is None:
            unit = self.units[key] = WriteUnit(lib.MODEL_VIEW, view_id, lib.FIELD_ARCH, lang, new_arch)
        unit.value = new_arch
        if change not in unit.changes:
            unit.changes.append(change)

    def stage_company(self, change: lib.Change, field_name: str, previous, value, backup_new) -> None:
        self.backup_entries.append(BackupEntry(
            change, lib.MODEL_COMPANY, self.company_id, field_name, None, previous, backup_new))
        key = (lib.MODEL_COMPANY, self.company_id, field_name, None)
        unit = self.units[key] = WriteUnit(lib.MODEL_COMPANY, self.company_id, field_name, None, value)
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

def _changed_on_server(ctx: SiteContext, change: lib.Change, current) -> Outcome | None:
    """Return a SKIP outcome when the server value no longer matches the CSV."""
    if ctx.args.force:
        return None
    if lib.normalize_text(current) != lib.normalize_text(change.valor_anterior):
        return Outcome(change, STATUS_SKIP,
                       f"changed on server since analysis (csv_prev={lib.truncate(change.valor_anterior)!r})",
                       lib.truncate(current))
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
        return Outcome(change, STATUS_SKIP, "already applied", lib.truncate(display))
    skip = _changed_on_server(ctx, change, current)
    if skip:
        return skip
    ctx.stage_company(change, field_name, previous, value, change.valor_nuevo)
    return Outcome(change, STATUS_PLAN, "", lib.truncate(display))


def prepare_company_image(ctx: SiteContext, change: lib.Change) -> Outcome:
    field_name = change.target.field
    path = Path(ctx.args.zip_root) / change.valor_nuevo.strip()
    if not path.is_file():
        return Outcome(change, STATUS_FAIL, f"image file not found: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    raw = ctx.company_value(field_name)
    current = raw if isinstance(raw, str) else ""
    current_display = f"<{len(current)} b64 chars>" if current else ""
    if current == encoded:
        return Outcome(change, STATUS_SKIP, "already applied", current_display)
    ctx.stage_company(change, field_name, current or None, encoded, change.valor_nuevo)
    return Outcome(change, STATUS_PLAN, f"{path.stat().st_size} bytes from {path.name}", current_display)


def _h2_or_none(arch: str, section: str) -> str | None:
    try:
        return lib.extract_section_h2(arch, section)
    except lib.SectionNotFound:
        return None


def _bg_or_none(arch: str, section: str) -> str | None:
    try:
        return lib.extract_section_bg(arch, section)
    except lib.SectionNotFound:
        return None


def prepare_view_h2(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id, section = change.target.view_id, change.target.section
    text = change.valor_nuevo
    current = _h2_or_none(ctx.original_arch(view_id, ctx.primary_lang), section)
    if current is None and not lib.find_section(ctx.work_arch(view_id, ctx.primary_lang), section):
        return Outcome(change, STATUS_FAIL, f"section {section!r} not found in view {view_id}")
    pending = [lang for lang in ctx.langs
               if _h2_or_none(ctx.work_arch(view_id, lang), section) != lib.normalize_text(text)]
    if not pending:
        return Outcome(change, STATUS_SKIP, "already applied", lib.truncate(current))
    skip = _changed_on_server(ctx, change, current)
    if skip:
        return skip
    for lang in pending:
        work = ctx.work_arch(view_id, lang)
        ctx.stage_arch(change, view_id, lang, lib.replace_section_h2(work, section, text))
    return Outcome(change, STATUS_PLAN, f"{len(pending)} language(s)", lib.truncate(current))


def _resolve_bg_url(ctx: SiteContext, change: lib.Change) -> tuple[str | None, str]:
    """Return (url, error). Zip paths must be uploaded by a sibling row."""
    value = change.valor_nuevo.strip()
    if value.startswith(lib.WEB_IMAGE_PREFIX):
        return value, ""
    section = change.target.section
    image_field = lib.SECTION_IMAGE_FIELD.get(section)
    if not image_field:
        return None, f"no res.company image field is mapped to section {section!r}"
    uploader = None
    for row in ctx.rows:
        if row.target.kind == lib.KIND_COMPANY_IMAGE and row.target.field == image_field \
                and row.valor_nuevo.strip() == value:
            uploader = row
            break
    if uploader is None:
        return None, f"no res_company.{image_field} row of site {ctx.site} uploads {value!r}"
    outcome = ctx.outcome_for(uploader)
    if outcome is None or outcome.status == STATUS_FAIL:
        return None, f"depends on failed row res_company.{image_field}"
    if outcome.status == STATUS_SKIP and outcome.reason != "already applied":
        return None, f"depends on skipped row res_company.{image_field} ({outcome.reason})"
    return f"{lib.WEB_IMAGE_PREFIX}{lib.MODEL_COMPANY}/{ctx.company_id}/{image_field}", ""


def prepare_view_bg(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id, section = change.target.view_id, change.target.section
    url, error = _resolve_bg_url(ctx, change)
    if error:
        return Outcome(change, STATUS_FAIL, error)
    current = _bg_or_none(ctx.original_arch(view_id, ctx.primary_lang), section)
    if current is None and not lib.find_section(ctx.work_arch(view_id, ctx.primary_lang), section):
        return Outcome(change, STATUS_FAIL, f"section {section!r} not found in view {view_id}")
    pending = [lang for lang in ctx.langs if _bg_or_none(ctx.work_arch(view_id, lang), section) != url]
    if not pending:
        return Outcome(change, STATUS_SKIP, "already applied", lib.truncate(current))
    skip = _changed_on_server(ctx, change, current)
    if skip:
        return skip
    for lang in pending:
        work = ctx.work_arch(view_id, lang)
        ctx.stage_arch(change, view_id, lang, lib.set_section_background(work, section, url))
    return Outcome(change, STATUS_PLAN, f"url={url} ({len(pending)} language(s))", lib.truncate(current))


def prepare_view_insert(ctx: SiteContext, change: lib.Change) -> Outcome:
    view_id = change.target.view_id
    text = change.valor_nuevo
    current = _h2_or_none(ctx.original_arch(view_id, ctx.primary_lang), "SEC1")
    pending = [lang for lang in ctx.langs
               if _h2_or_none(ctx.work_arch(view_id, lang), "SEC1") != lib.normalize_text(text)]
    if not pending:
        return Outcome(change, STATUS_SKIP, "already applied", lib.truncate(current))
    skip = _changed_on_server(ctx, change, current)
    if skip:
        return skip
    staged = 0
    for lang in pending:
        work = ctx.work_arch(view_id, lang)
        if lib.find_section(work, "SEC1"):
            if not ctx.args.force:
                return Outcome(change, STATUS_FAIL,
                               f"SEC1 already present in {lang} with a different heading (use --force)",
                               lib.truncate(current))
            new_arch = lib.replace_section_h2(work, "SEC1", text)
        else:
            new_arch = lib.insert_sec1_after_hero(work, text)
        ctx.stage_arch(change, view_id, lang, new_arch)
        staged += 1
    return Outcome(change, STATUS_PLAN, f"{staged} language(s)", lib.truncate(current))


PREPARERS = {
    lib.KIND_COMPANY_FIELD: prepare_company_field,
    lib.KIND_COMPANY_IMAGE: prepare_company_image,
    lib.KIND_VIEW_H2: prepare_view_h2,
    lib.KIND_VIEW_BG: prepare_view_bg,
    lib.KIND_VIEW_INSERT: prepare_view_insert,
}


def prepare_site(client, site: int, rows: list[lib.Change], langs: list[str], args) -> SiteContext | list[Outcome]:
    """Read current values and decide every row of one site.

    Returns the :class:`SiteContext` or, when the site itself cannot be
    resolved, a list of FAIL outcomes."""
    try:
        company_id = client.company_of_website(site)
    except lib.OdooError as exc:
        return [Outcome(row, STATUS_FAIL, f"cannot resolve company: {exc}") for row in rows]
    ctx = SiteContext(client, site, company_id, langs, args, rows)
    for change in rows:
        try:
            outcome = PREPARERS[change.target.kind](ctx, change)
        except (lib.OdooError, lib.ArchError, OSError, ValueError) as exc:
            outcome = Outcome(change, STATUS_FAIL, f"{type(exc).__name__}: {exc}")
        ctx.outcomes.append(outcome)
    return ctx


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def write_backup(backup: lib.BackupWriter, contexts: list[SiteContext]) -> None:
    for ctx in contexts:
        for entry in ctx.backup_entries:
            backup.append_backup(
                site=ctx.site, campo=entry.change.campo, model=entry.model, res_id=entry.res_id,
                field=entry.field, lang=entry.lang, valor_anterior=entry.valor_anterior,
                valor_nuevo=entry.valor_nuevo)
    backup.flush()


def execute_site(ctx: SiteContext, backup: lib.BackupWriter, stop_on_error: bool) -> bool:
    """Perform the staged writes of one site. Returns False on an error when
    ``stop_on_error`` is set."""
    for unit in ctx.units.values():
        context = {"lang": unit.lang} if unit.lang else None
        try:
            ctx.client.write(unit.model, [unit.res_id], {unit.field: unit.value}, context)
            unit.done = True
        except lib.OdooError as exc:
            unit.error = str(exc)
            print(f"  ERROR writing {unit.model}[{unit.res_id}].{unit.field} lang={unit.lang}: {exc}")
            if stop_on_error:
                _finalize_outcomes(ctx)
                return False
            continue
        for change in unit.changes:
            backup.append_applied(site=ctx.site, campo=change.campo, model=unit.model,
                                  res_id=unit.res_id, field=unit.field, lang=unit.lang)
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


def print_summary(outcomes: list[Outcome], apply: bool, backup_path: Path | None) -> None:
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
    print(f"  failed:  {counts[STATUS_FAIL]}")
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
    parser.add_argument("--backup", type=Path, default=lib.DEFAULT_BACKUP, help="backup JSON lines file")
    parser.add_argument("--apply", action="store_true", help="perform the writes (default: dry-run)")
    parser.add_argument("--offline", action="store_true",
                        help="print the plan from the CSV alone, without connecting")
    parser.add_argument("--batch-size", type=int, default=10, help="sites per batch")
    parser.add_argument("--only-site", type=lib.parse_site_list, default=None,
                        help="comma separated website ids to process")
    parser.add_argument("--min-confianza", type=float, default=0.85,
                        help="rows with a lower confianza are skipped")
    parser.add_argument("--from-batch", type=int, default=1, help="resume from this batch number (1-based)")
    parser.add_argument("--stop-on-error", action="store_true",
                        help="abort on the first failed write instead of continuing")
    parser.add_argument("--force", action="store_true",
                        help="write even if the server value differs from valor_anterior")
    parser.add_argument("--primary-lang", default=lib.DEFAULT_PRIMARY_LANG,
                        help="language used to compare view values with valor_anterior")
    return parser


def select_changes(changes: list[lib.Change], args) -> tuple[list[lib.Change], list[Outcome]]:
    """Apply --only-site and --min-confianza. Returns (kept, skipped outcomes)."""
    kept, skipped = [], []
    for change in changes:
        if args.only_site is not None and change.site not in args.only_site:
            continue
        if change.confianza < args.min_confianza:
            skipped.append(Outcome(change, STATUS_SKIP,
                                   f"confianza {change.confianza:.2f} < {args.min_confianza:.2f}"))
            continue
        kept.append(change)
    return kept, skipped


def run_offline(grouped: dict[int, list[lib.Change]], args) -> None:
    site_batches = list(lib.batches(list(grouped), args.batch_size))
    for number, sites in enumerate(site_batches, start=1):
        print(f"[batch {number}/{len(site_batches)}] sites {', '.join(map(str, sites))}")
        for site in sites:
            print(f" site {site}")
            for change in grouped[site]:
                print(f"  {change.campo:<45} PLAN         | csv_prev={lib.truncate(change.valor_anterior)!r}"
                      f" | new={lib.truncate(change.valor_nuevo)!r} | confianza={change.confianza:.2f}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1 or args.from_batch < 1:
        print("--batch-size and --from-batch must be >= 1", file=sys.stderr)
        return 2
    try:
        changes = lib.load_changes(args.csv)
    except (OSError, ValueError, lib.CampoError) as exc:
        print(f"cannot load {args.csv}: {exc}", file=sys.stderr)
        return 2
    kept, outcomes = select_changes(changes, args)
    for outcome in outcomes:
        print(f"  site {outcome.change.site} {outcome.change.campo}: SKIP | {outcome.reason}")
    grouped = lib.group_by_site(kept)
    print(f"{len(kept)} row(s) across {len(grouped)} site(s); {len(outcomes)} skipped by confianza")

    if args.offline:
        run_offline(grouped, args)
        print_summary(outcomes + [Outcome(c, STATUS_PLAN) for c in kept], apply=False, backup_path=None)
        return 0

    try:
        client = lib.client_from_args(args)
    except lib.OdooError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    langs = client.language_codes()
    if not langs:
        print("no active languages found", file=sys.stderr)
        return 2
    print(f"connected to {args.url} db={args.db} uid={client.uid}; languages: {', '.join(langs)}")
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
                print(f" site {site} (company {prepared.company_id}, primary lang {prepared.primary_lang})")
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

    print_summary(outcomes, apply=args.apply, backup_path=args.backup if args.apply else None)
    if stopped:
        print("stopped on error (--stop-on-error)")
    failed = any(o.status == STATUS_FAIL for o in outcomes)
    return 1 if failed or stopped else 0


if __name__ == "__main__":
    sys.exit(main())
