#!/usr/bin/env python3
"""Restore the values recorded in ``backup.jsonl`` by ``aplicar.py``.

For every (model, res_id, field, lang) the EARLIEST ``backup`` line is used,
so running ``aplicar.py`` twice still restores the original value.

Which values are restored (event semantics of the backup file):

* ``backup`` line only: the write was never attempted (the batch was
  interrupted before it, or a dependency failed). Skipped by default;
  restored with ``--include-unapplied``.
* ``pending`` line: ``aplicar.py`` flushed it immediately before the RPC
  write. If no ``applied`` line follows, the process died mid-write and the
  server value is unknown, so the value IS restored by default.
* ``applied`` line: the write succeeded. Restored by default.

Company fields and images are restored through XML-RPC ``write``; before
each write the current value is read and the restore is skipped when it
already equals the backed-up value.

Views are NOT restored through the ORM: ``arch_db`` is an xml_translate
field and a write in one language rebuilds every other language from it, so
restoring language by language would mix languages. The view backup line
holds the arch of every language (``{lang: arch}``) and each view is
restored with one SQL statement that replaces the whole jsonb value::

    UPDATE ir_ui_view SET arch_db = <backup dict>::jsonb WHERE id = <id>

All the view statements of a batch run in ONE transaction through
``docker exec -i <--container> psql -U odoo -d <--pg-db> -v ON_ERROR_STOP=1``,
followed by ``INSERT INTO orm_signaling_templates DEFAULT VALUES`` so every
Odoo worker drops its template cache. Each UPDATE must touch exactly one
row or the whole transaction is aborted. A view is skipped when every
backed-up language already reads back equal to the backup.

Only whole-view backup lines (``lang`` null, ``valor_anterior`` a dict) are
accepted; the old per-language view lines are rejected with an error.

Dry-run by default (views: languages, sizes and whether the current primary
language differs are printed, nothing is executed); ``--apply`` performs the
writes. The default backup path lives outside the git tree
(``/home/odoo/Pending/jev-work/backup.jsonl``).
"""
from __future__ import annotations

import argparse
import json
import re
import secrets
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import jev_apply_lib as lib

STATUS_PLAN = "WOULD RESTORE"
STATUS_RESTORED = "RESTORED"
STATUS_SKIP = "SKIP"
STATUS_FAIL = "FAIL"

DEFAULT_CONTAINER = "odoo-canariasconectada-dooba-gbb617-db-1"
DEFAULT_PG_DB = "prod"
PG_USER = "odoo"
PSQL_TIMEOUT = 600

_LANG_CODE_RE = re.compile(r"^[a-z]{2,3}(?:_[A-Za-z0-9]+)?(?:@[A-Za-z0-9]+)?$")
_DOCKER_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


class RestoreError(RuntimeError):
    """The SQL restore of a batch of views failed (nothing was committed)."""


@dataclass
class Restore:
    """One value to write back."""

    site: int
    campo: str
    model: str
    res_id: int
    field: str
    lang: str | None
    valor_anterior: object
    applied: bool
    line: int
    ts: str = ""
    primary_lang: str = lib.DEFAULT_PRIMARY_LANG
    status: str = ""
    reason: str = ""

    @property
    def is_view(self) -> bool:
        return self.model == lib.MODEL_VIEW

    @property
    def label(self) -> str:
        if self.is_view:
            return f"{lib.MODEL_VIEW}[{self.res_id}] ({self.campo})"
        lang = f" [{self.lang}]" if self.lang else ""
        return f"{self.campo}{lang}"


def validate_view_archs(value, where: str) -> dict[str, str]:
    """Check a view backup value: a non-empty ``{lang: arch}`` dict with
    valid language codes, non-empty string archs and the ``en_US`` fallback.
    Raises ``ValueError``."""
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{where}: view backup must hold a {{lang: arch}} dict of every language")
    for lang, arch in value.items():
        if not isinstance(lang, str) or not _LANG_CODE_RE.match(lang):
            raise ValueError(f"{where}: invalid language code {lang!r}")
        if not isinstance(arch, str) or not arch.strip():
            raise ValueError(f"{where}: empty or non-text arch for {lang}")
    if lib.FALLBACK_LANG not in value:
        raise ValueError(f"{where}: view backup lacks the {lib.FALLBACK_LANG} fallback arch")
    return value


def _check_view_record(record: dict, event: str) -> None:
    """Reject old per-language view lines and malformed whole-view lines."""
    where = f"backup line {record.get('_line')}"
    if record.get("lang") is not None:
        raise ValueError(
            f"{where}: per-language view entry (lang={record.get('lang')!r}) is the old backup format; "
            "it cannot be restored safely (each ORM write rebuilds the other languages). "
            "Only whole-view backups written by the current aplicar.py are supported")
    if event == lib.EVENT_BACKUP:
        validate_view_archs(record.get("valor_anterior"), where)


def collect_restores(records: list[dict]) -> list[Restore]:
    """Reduce backup lines to one :class:`Restore` per value identity.

    ``Restore.applied`` is True when an ``applied`` or ``pending`` event
    exists for the key (the write was confirmed or at least attempted).
    Raises ``ValueError`` on old-format or malformed view lines."""
    earliest: dict[tuple, Restore] = {}
    applied_keys: set[tuple] = set()
    for record in records:
        event = record.get("event", lib.EVENT_BACKUP if "valor_anterior" in record else lib.EVENT_APPLIED)
        if record.get("model") == lib.MODEL_VIEW:
            _check_view_record(record, event)
        key = lib.backup_key(record)
        if event in (lib.EVENT_APPLIED, lib.EVENT_PENDING) or record.get("applied") is True:
            # A pending line means the write was attempted: restore it too.
            applied_keys.add(key)
        if event != lib.EVENT_BACKUP:
            continue
        candidate = Restore(
            site=int(record["site"]), campo=record["campo"], model=record["model"],
            res_id=int(record["res_id"]), field=record["field"], lang=record.get("lang"),
            valor_anterior=record.get("valor_anterior"), applied=False, line=record["_line"],
            ts=record.get("ts", ""), primary_lang=record.get("primary_lang") or lib.DEFAULT_PRIMARY_LANG)
        current = earliest.get(key)
        if current is None or (candidate.ts, candidate.line) < (current.ts, current.line):
            earliest[key] = candidate
    for key, restore in earliest.items():
        restore.applied = key in applied_keys
    return sorted(earliest.values(), key=lambda r: (r.site, r.model, r.res_id, r.field, r.lang or "", r.line))


def restore_value(restore: Restore):
    """Value to send through ``write`` (``False`` when the original was empty)."""
    value = restore.valor_anterior
    if value is None or value == "":
        return False
    return value


def current_matches(client: lib.OdooClient, restore: Restore) -> tuple[bool, object]:
    """Read the current server value; return (already_original, current)."""
    context = {"lang": restore.lang} if restore.lang else None
    record = client.read_one(restore.model, restore.res_id, [restore.field], context)
    current = record.get(restore.field)
    if restore.field == "category_id":
        current = int(current[0]) if isinstance(current, (list, tuple)) and current else None
    if current is False:
        current = None
    target = restore.valor_anterior
    if target == "":
        target = None
    return current == target, current


def describe(restore: Restore, value) -> str:
    if value is None or value is False:
        return "<empty>"
    if restore.field in lib.COMPANY_IMAGE_FIELDS:
        return f"<{len(str(value))} b64 chars>"
    if restore.field == lib.FIELD_ARCH:
        text = str(value)
        return f"<arch {len(text)} chars>"
    return lib.truncate(value)


def print_restore(restore: Restore, current=None) -> None:
    parts = [f"  {restore.label:<55} {restore.status:<14}"]
    if current is not None:
        parts.append(f"current={describe(restore, current)}")
    parts.append(f"restore={describe(restore, restore.valor_anterior)}")
    if restore.reason:
        parts.append(restore.reason)
    print(" | ".join(parts))


# ---------------------------------------------------------------------------
# Views: whole jsonb restore through psql
# ---------------------------------------------------------------------------

def view_differences(client: lib.OdooClient, restore: Restore) -> dict[str, bool]:
    """``{lang: current arch differs from the backup}`` for every backed-up
    language, read through XML-RPC with that language in the context."""
    diffs = {}
    for lang, arch in restore.valor_anterior.items():
        record = client.read_one(lib.MODEL_VIEW, restore.res_id, [lib.FIELD_ARCH], {"lang": lang})
        diffs[lang] = record.get(lib.FIELD_ARCH) != arch
    return diffs


def describe_view(restore: Restore, diffs: dict[str, bool] | None) -> str:
    archs = restore.valor_anterior
    sizes = ", ".join(f"{lang}={len(archs[lang])}" for lang in lib.order_languages(archs, restore.primary_lang))
    parts = [f"languages: {sizes} chars"]
    if diffs is not None:
        primary = restore.primary_lang
        state = "unknown" if primary not in diffs else ("yes" if diffs[primary] else "no")
        parts.append(f"current {primary} differs: {state}")
        parts.append(f"{sum(diffs.values())}/{len(diffs)} language(s) differ")
    return " | ".join(parts)


def print_view_restore(restore: Restore, diffs: dict[str, bool] | None, status: str = "") -> None:
    parts = [f"  {restore.label:<55} {status or restore.status:<14}", describe_view(restore, diffs)]
    if restore.reason:
        parts.append(restore.reason)
    print(" | ".join(parts))


def _dollar_tag(payloads: list[str]) -> str:
    """A random dollar-quote tag that occurs in none of the payloads."""
    while True:
        tag = f"$jev_{secrets.token_hex(8)}$"
        if not any(tag in payload for payload in payloads):
            return tag


def build_view_restore_sql(restores: list[Restore]) -> str:
    """One psql script restoring the full ``arch_db`` jsonb of every view in
    a single transaction, then signalling the template cache.

    The JSON is produced by ``json.dumps`` (ASCII only) and embedded with a
    random dollar-quote tag checked not to occur in any payload; view ids
    must be positive ints. Each UPDATE runs inside a CTE whose ``1 /
    count(*)`` raises division_by_zero when no row was updated, which with
    ``ON_ERROR_STOP`` aborts the whole transaction."""
    if not restores:
        raise ValueError("no view to restore")
    items = []
    for restore in restores:
        view_id = restore.res_id
        if type(view_id) is not int or view_id <= 0:
            raise ValueError(f"invalid view id {view_id!r}")
        archs = validate_view_archs(restore.valor_anterior, f"view {view_id}")
        items.append((view_id, json.dumps(archs, ensure_ascii=True, sort_keys=True)))
    tag = _dollar_tag([payload for _view_id, payload in items])
    lines = ["BEGIN;"]
    for view_id, payload in items:
        lines.append(
            f"WITH restored AS (UPDATE ir_ui_view SET arch_db = {tag}{payload}{tag}::jsonb "
            f"WHERE id = {view_id:d} RETURNING id) SELECT 1 / count(*) FROM restored;")
    lines.append("INSERT INTO orm_signaling_templates DEFAULT VALUES;")
    lines.append("COMMIT;")
    return "\n".join(lines) + "\n"


def psql_command(container: str, pg_db: str) -> list[str]:
    for label, value in (("container", container), ("pg-db", pg_db)):
        if not _DOCKER_NAME_RE.match(value or ""):
            raise ValueError(f"invalid --{label} {value!r}")
    return ["docker", "exec", "-i", container, "psql", "-X", "-q", "-t", "-A",
            "-U", PG_USER, "-d", pg_db, "-v", "ON_ERROR_STOP=1"]


def run_view_restore_sql(script: str, container: str, pg_db: str) -> None:
    """Feed ``script`` to psql on stdin. Raises :class:`RestoreError`."""
    command = psql_command(container, pg_db)
    try:
        result = subprocess.run(command, input=script, text=True, capture_output=True,
                                timeout=PSQL_TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RestoreError(f"psql could not run: {exc}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip().splitlines()
        raise RestoreError(f"psql exited with {result.returncode}: {detail[-1] if detail else 'no output'}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore values from backup.jsonl (dry-run by default): company values through "
                    "XML-RPC, views through one psql transaction per batch.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    lib.add_connection_args(parser)
    parser.add_argument("--backup", type=Path, default=lib.DEFAULT_BACKUP, help="backup JSON lines file")
    parser.add_argument("--apply", action="store_true", help="perform the writes (default: dry-run)")
    parser.add_argument("--only-site", type=lib.parse_site_list, default=None,
                        help="comma separated website ids to restore")
    parser.add_argument("--batch-size", type=int, default=10, help="sites per batch")
    parser.add_argument("--include-unapplied", action="store_true",
                        help="also restore values that only have a 'backup' line (write never attempted)")
    parser.add_argument("--stop-on-error", action="store_true", help="abort on the first failed write")
    parser.add_argument("--container", default=DEFAULT_CONTAINER,
                        help="docker container running PostgreSQL (view restores)")
    parser.add_argument("--pg-db", default=DEFAULT_PG_DB, help="PostgreSQL database (view restores)")
    return parser


def restore_company(client: lib.OdooClient, restore: Restore, apply: bool) -> None:
    current = None
    try:
        same, current = current_matches(client, restore)
        if same:
            restore.status, restore.reason = STATUS_SKIP, "already at original value"
        elif apply:
            context = {"lang": restore.lang} if restore.lang else None
            client.write(restore.model, [restore.res_id], {restore.field: restore_value(restore)}, context)
            restore.status = STATUS_RESTORED
        else:
            restore.status = STATUS_PLAN
    except lib.OdooError as exc:
        restore.status, restore.reason, current = STATUS_FAIL, str(exc), None
    print_restore(restore, current)


def restore_views(client: lib.OdooClient, views: list[Restore], args) -> bool:
    """Check and (with ``--apply``) restore the views of one batch in a
    single SQL transaction. Returns False when the batch failed."""
    todo: list[Restore] = []
    ok = True
    for restore in views:
        diffs = None
        try:
            diffs = view_differences(client, restore)
            if not any(diffs.values()):
                restore.status, restore.reason = STATUS_SKIP, "already at original value (all languages)"
            else:
                restore.status = STATUS_PLAN
                todo.append(restore)
        except lib.OdooError as exc:
            restore.status, restore.reason, ok = STATUS_FAIL, str(exc), False
        # With --apply the SQL runs after every view of the batch is checked.
        print_view_restore(restore, diffs, "TO RESTORE" if args.apply and restore.status == STATUS_PLAN else "")
        if not ok and args.stop_on_error:
            return False
    if not todo or not args.apply:
        return ok
    try:
        run_view_restore_sql(build_view_restore_sql(todo), args.container, args.pg_db)
    except (RestoreError, ValueError) as exc:
        for restore in todo:
            restore.status, restore.reason = STATUS_FAIL, f"SQL transaction rolled back: {exc}"
        print(f"  ERROR restoring {len(todo)} view(s), nothing committed: {exc}")
        return False
    for restore in todo:
        restore.status = STATUS_RESTORED
    print(f"  restored {len(todo)} view(s) in one transaction: "
          f"{', '.join(str(r.res_id) for r in todo)} (template cache signalled)")
    return ok


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1:
        print("--batch-size must be >= 1", file=sys.stderr)
        return 2
    try:
        psql_command(args.container, args.pg_db)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    try:
        records = lib.read_backup(args.backup)
        restores = collect_restores(records)
    except (OSError, ValueError) as exc:
        print(f"cannot load {args.backup}: {exc}", file=sys.stderr)
        return 2
    if args.only_site is not None:
        restores = [r for r in restores if r.site in args.only_site]
    print(f"{len(records)} backup line(s) -> {len(restores)} value(s) to consider")

    grouped: dict[int, list[Restore]] = {}
    for restore in restores:
        if not restore.applied and not args.include_unapplied:
            restore.status, restore.reason = STATUS_SKIP, "write never attempted (use --include-unapplied)"
            if restore.is_view:
                print_view_restore(restore, None)
            else:
                print_restore(restore)
            continue
        grouped.setdefault(restore.site, []).append(restore)

    try:
        client = lib.client_from_args(args)
    except lib.OdooError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"connected to {args.url} db={args.db} uid={client.uid}; views via docker "
          f"{args.container} psql db={args.pg_db}")
    mode = "APPLY" if args.apply else "DRY-RUN"

    stopped = False
    site_batches = list(lib.batches(sorted(grouped), args.batch_size))
    for number, sites in enumerate(site_batches, start=1):
        print(f"\n[{mode} batch {number}/{len(site_batches)}] sites {', '.join(map(str, sites))}")
        views: list[Restore] = []
        for site in sites:
            print(f" site {site}")
            for restore in grouped[site]:
                if restore.is_view:
                    views.append(restore)
                    continue
                restore_company(client, restore, args.apply)
                if restore.status == STATUS_FAIL and args.stop_on_error:
                    stopped = True
                    break
            if stopped:
                break
        if stopped:
            break
        if views:
            print(f" views of batch {number}")
            if not restore_views(client, views, args) and args.stop_on_error:
                stopped = True
                break

    counts = {}
    for restore in restores:
        counts[restore.status or "pending"] = counts.get(restore.status or "pending", 0) + 1
    print()
    print("Summary:")
    for status in (STATUS_RESTORED, STATUS_PLAN, STATUS_SKIP, STATUS_FAIL, "pending"):
        if counts.get(status):
            print(f"  {status.lower()}: {counts[status]}")
    if stopped:
        print("stopped on error (--stop-on-error)")
    failed = counts.get(STATUS_FAIL, 0) > 0
    return 1 if failed or stopped else 0


if __name__ == "__main__":
    sys.exit(main())
