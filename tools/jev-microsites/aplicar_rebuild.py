#!/usr/bin/env python3
"""``Homepage.rebuild`` rows of ``aplicar.py``: planning and offline checks.

A rebuild row (``ir_ui_view.<view_id>.Homepage.rebuild``) replaces the whole
homepage arch, EVERY language, by the ``arch_after_<view_id>.json`` file that
``normalizar_portada.py`` produced (``valor_nuevo`` is the file name relative to
``--arch-root``; ``valor_anterior`` the section list of the page at analysis
time). The write itself is done by ``aplicar.py`` in two RPC calls on one
backup line (the arch of every language, as for any view write):

1. ``write(arch_db)`` of the primary language. Odoo rebuilds the other
   languages from it: unchanged terms keep their translation, new ones read
   Spanish.
2. ``update_field_translations(arch_db, {lang: {primary_term: term}},
   source_lang=primary)`` with the terms of the file's other languages, so
   every language holds exactly the proposed arch.

Both calls carry ``auto_translate_skip`` so the website_auto_translate queue
does not machine-translate over the texts taken from the reference.

Rebuild rows are exclusive on their view (no other ``ir_ui_view.<id>.*`` row
of the same view in the CSV) and use their own backup file
(``jev_apply_lib.REBUILD_BACKUP``), never the September or strip-2 files.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import jev_apply_lib as lib
import jev_rebuild_lib as rb
import jev_rebuild_terms as terms

WRITE_CONTEXT = {"auto_translate_skip": True}


@dataclass
class RebuildPlan:
    """Decision for one rebuild row (consumed by ``aplicar.prepare_view_rebuild``)."""

    current: str = ""                 # section list of the primary arch on the server
    error: str = ""                   # FAIL
    done: bool = False                # SKIP: already applied
    drift: str = ""                   # SKIP unless --force
    note: str = ""
    archs: dict = field(default_factory=dict)    # {lang: arch} to apply
    before: dict = field(default_factory=dict)   # {lang: arch} on the server (backup)
    mapping: dict = field(default_factory=dict)  # {lang: {primary_term: term}}


def arch_file_path(arch_root: Path, value: str) -> Path:
    """``valor_nuevo`` resolved under ``arch_root`` (containment rules of
    :func:`jev_apply_lib.zip_image_path`); must be an ``arch_after_*.json``."""
    path = lib.zip_image_path(arch_root, value)
    if not (path.name.startswith("arch_after_") and path.suffix == ".json"):
        raise ValueError(f"rebuild file must be an arch_after_<view_id>.json, got {value!r}")
    return path


def load_after_archs(path: Path, view_id: int) -> dict[str, str]:
    """The ``{lang: arch}`` object of a proposal file, checked for shape and
    for naming the right view. Raises ``ValueError``."""
    if path.name != f"arch_after_{view_id}.json":
        raise ValueError(f"{path.name} does not belong to view {view_id}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or not data or not all(
            isinstance(lang, str) and isinstance(arch, str) and arch.strip() for lang, arch in data.items()):
        raise ValueError(f"{path.name}: expected a non-empty {{lang: arch}} object")
    return data


def other_view_rows(change: lib.Change, rows: list[lib.Change]) -> list[str]:
    return [row.campo for row in rows
            if row is not change and row.target.model == lib.MODEL_VIEW and row.target.view_id == change.target.view_id]


def validate_offline_rebuild(change: lib.Change, rows: list[lib.Change], arch_root: Path) -> str:
    """File, shape, XML and term alignment checks without a server."""
    others = other_view_rows(change, rows)
    if others:
        return f"rebuild row cannot be combined with other rows of the same view: {', '.join(others)}"
    try:
        archs = load_after_archs(arch_file_path(arch_root, change.valor_nuevo), change.target.view_id)
    except ValueError as exc:
        return str(exc)
    primary = lib.DEFAULT_PRIMARY_LANG if lib.DEFAULT_PRIMARY_LANG in archs else None
    if primary is None or lib.FALLBACK_LANG not in archs:
        return f"arch file must hold {lib.DEFAULT_PRIMARY_LANG} and {lib.FALLBACK_LANG}, got {sorted(archs)}"
    try:
        terms.translation_mapping(archs, primary)
    except terms.TermError as exc:
        return str(exc)
    return ""


def plan_rebuild(change: lib.Change, rows: list[lib.Change], arch_root: Path,
                 read_archs: Callable[[], dict[str, str]], primary: str, langs: list[str]) -> RebuildPlan:
    """Decide a rebuild row against the server archs (``read_archs`` reads
    every language, lazily so a bad file fails before any RPC)."""
    plan = RebuildPlan()
    error = validate_offline_rebuild(change, rows, arch_root)
    if error:
        plan.error = error
        return plan
    archs = load_after_archs(arch_file_path(arch_root, change.valor_nuevo), change.target.view_id)
    if set(archs) != set(langs):
        plan.error = f"arch file languages {sorted(archs)} differ from the server languages {sorted(langs)}"
        return plan
    if primary not in archs:
        plan.error = f"arch file lacks the primary language {primary}"
        return plan
    before = read_archs()
    plan.before, plan.archs = before, archs
    plan.current = rb.section_list(before[primary])
    if all(lib.normalize_text(before.get(lang)) == lib.normalize_text(arch) for lang, arch in archs.items()):
        plan.done = True
        return plan
    if lib.normalize_text(plan.current) != lib.normalize_text(change.valor_anterior):
        plan.drift = (f"changed on server since analysis (sections now {plan.current!r}, "
                      f"csv_prev={change.valor_anterior!r})")
    else:
        kept = rb.extract_site_texts(archs[primary]).preserved()
        now = rb.extract_site_texts(before[primary]).preserved()
        # A section the page did not have (strip added, SEC1 omitted) has no text to compare.
        changed = [key for key in ("h1", "sec1", "separador") if now[key] and kept[key] and kept[key] != now[key]]
        changed += [f"Acerca col{n}" for n, texts in kept["columns"].items() if now["columns"].get(n) != texts]
        if changed:
            plan.drift = f"texts changed on server since analysis: {', '.join(changed)}"
    try:
        plan.mapping = terms.translation_mapping(archs, primary)
    except terms.TermError as exc:
        plan.error = str(exc)
        return plan
    translated = sum(1 for pairs in plan.mapping.values() if pairs)
    plan.note = (f"{plan.current} -> {rb.section_list(archs[primary])}; {len(archs)} languages, "
                 f"{translated} with term translations")
    return plan


def has_rebuild_rows(changes: list[lib.Change], invalid: list[lib.InvalidRow]) -> bool:
    return any(c.target.kind == lib.KIND_VIEW_REBUILD for c in changes) or any(
        f".{lib.REBUILD_SECTION}.rebuild" in row.campo for row in invalid)


def resolve_rebuild_backup(args, changes: list[lib.Change], invalid: list[lib.InvalidRow], strip: bool) -> str | None:
    """Backup file rule for rebuild rows: ``None`` when the CSV has none
    (caller decides), ``""`` when fine, else the error message. Rebuild rows
    get :data:`jev_apply_lib.REBUILD_BACKUP` by default and are refused
    against the September and strip-2 files, and mixed with strip-2 title
    rows (two backup policies in one run)."""
    if not has_rebuild_rows(changes, invalid):
        return None
    if strip:
        return "refusing to mix Homepage.rebuild rows with strip-2 title rows: run them from separate CSVs"
    if args.backup is None:
        args.backup = lib.REBUILD_BACKUP
    for reserved in (lib.DEFAULT_BACKUP, lib.S2_BACKUP):
        if lib.same_path(args.backup, reserved):
            return (f"refusing to use {reserved} for Homepage.rebuild rows: it holds earlier backups of the same "
                    f"views (revertir.py restores the earliest line); use --backup {lib.REBUILD_BACKUP}")
    return ""
