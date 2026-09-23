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

Dry-run by default; ``--apply`` performs the writes. Before each write the
current server value is read and the restore is skipped when it already
equals the backed-up value. The default backup path lives outside the git
tree (``/home/odoo/Pending/jev-work/backup.jsonl``).
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import jev_apply_lib as lib

STATUS_PLAN = "WOULD RESTORE"
STATUS_RESTORED = "RESTORED"
STATUS_SKIP = "SKIP"
STATUS_FAIL = "FAIL"


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
    status: str = ""
    reason: str = ""

    @property
    def label(self) -> str:
        lang = f" [{self.lang}]" if self.lang else ""
        return f"{self.campo}{lang}"


def collect_restores(records: list[dict]) -> list[Restore]:
    """Reduce backup lines to one :class:`Restore` per value identity.

    ``Restore.applied`` is True when an ``applied`` or ``pending`` event
    exists for the key (the write was confirmed or at least attempted)."""
    earliest: dict[tuple, Restore] = {}
    applied_keys: set[tuple] = set()
    for record in records:
        event = record.get("event", lib.EVENT_BACKUP if "valor_anterior" in record else lib.EVENT_APPLIED)
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
            ts=record.get("ts", ""))
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Restore values from backup.jsonl through XML-RPC (dry-run by default).",
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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1:
        print("--batch-size must be >= 1", file=sys.stderr)
        return 2
    try:
        records = lib.read_backup(args.backup)
    except (OSError, ValueError) as exc:
        print(f"cannot load {args.backup}: {exc}", file=sys.stderr)
        return 2
    restores = collect_restores(records)
    if args.only_site is not None:
        restores = [r for r in restores if r.site in args.only_site]
    print(f"{len(records)} backup line(s) -> {len(restores)} value(s) to consider")

    grouped: dict[int, list[Restore]] = {}
    for restore in restores:
        if not restore.applied and not args.include_unapplied:
            restore.status, restore.reason = STATUS_SKIP, "write never attempted (use --include-unapplied)"
            print_restore(restore)
            continue
        grouped.setdefault(restore.site, []).append(restore)

    try:
        client = lib.client_from_args(args)
    except lib.OdooError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(f"connected to {args.url} db={args.db} uid={client.uid}")
    mode = "APPLY" if args.apply else "DRY-RUN"

    stopped = False
    site_batches = list(lib.batches(sorted(grouped), args.batch_size))
    for number, sites in enumerate(site_batches, start=1):
        print(f"\n[{mode} batch {number}/{len(site_batches)}] sites {', '.join(map(str, sites))}")
        for site in sites:
            print(f" site {site}")
            for restore in grouped[site]:
                try:
                    same, current = current_matches(client, restore)
                    if same:
                        restore.status, restore.reason = STATUS_SKIP, "already at original value"
                    elif args.apply:
                        context = {"lang": restore.lang} if restore.lang else None
                        client.write(restore.model, [restore.res_id],
                                     {restore.field: restore_value(restore)}, context)
                        restore.status = STATUS_RESTORED
                    else:
                        restore.status = STATUS_PLAN
                except lib.OdooError as exc:
                    restore.status, restore.reason, current = STATUS_FAIL, str(exc), None
                print_restore(restore, current)
                if restore.status == STATUS_FAIL and args.stop_on_error:
                    stopped = True
                    break
            if stopped:
                break
        if stopped:
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
