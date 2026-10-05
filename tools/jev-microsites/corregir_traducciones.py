#!/usr/bin/env python3
"""Replace the machine translation of the new microsite sentences by reviewed ones.

Uses the website_auto_translate correction path: writing ``translated_text``
on an ``auto.translate.term`` applies the sentence to the page in that language
and locks it, so the machine never overwrites it again (the module's
documented behaviour for hand corrections).

Input: a JSON file {spanish_source_text: {lang: translation}}; only rows whose
Jev QA verdict is "ok" in the optional --qa file are written. Keys are the
text as stored in the arch (``&`` as ``&amp;``), which is also how the terms
store their ``source_text``.

The views to touch come from ``--views`` (term_rows.json of the 2026-09-23
extraction) or, for a proposals CSV such as ``cambios_s2.csv``, from
``--views-csv`` (every ``ir_ui_view.<id>.*`` row). The terms only exist once
``website_auto_translate`` has processed the queue that the es_ES write of
``aplicar.py --apply`` enqueued (10 jobs every 5 minutes), so run this after
the queue is done. Strip-2 titles, for example::

    python3 corregir_traducciones.py --translations s2_translations.json \\
        --qa s2_translations_qa.json --views-csv cambios_s2.csv          # dry-run
    python3 corregir_traducciones.py ... --apply

Dry-run by default; ``--apply`` writes. Every previous value is appended to
--backup (JSON lines) before its write. Run through con_credenciales.sh.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402

WORK = Path("/home/odoo/Pending/jev-work")


def view_ids_from_args(views: str | None, views_csv: str | None) -> list[int]:
    """View ids from a proposals CSV (``--views-csv``) or term_rows.json (``--views``)."""
    if views_csv:
        changes, invalid = lib.load_changes(Path(views_csv))
        if invalid:
            raise ValueError(f"{views_csv}: {len(invalid)} unparsable row(s), first: {invalid[0].error}")
        return lib.view_ids_of_changes(changes)
    return sorted({int(r["v"]) for r in json.loads(Path(views).read_text(encoding="utf-8"))})


def plan_term_writes(terms: list[dict], translations: dict, qa: dict | None) -> tuple[list[tuple[dict, str]], dict]:
    """Decide which terms get a reviewed translation.

    Returns ``(todo, counts)``: ``todo`` is ``[(term, new_text)]`` and
    ``counts`` has ``same`` (already holds it), ``held_back`` (Jev QA not
    ok) and ``unknown`` (sentence not in the translations file)."""
    todo: list[tuple[dict, str]] = []
    counts = {"same": 0, "held_back": 0, "unknown": 0}
    for term in terms:
        per_lang = translations.get(term["source_text"])
        if not per_lang:
            counts["unknown"] += 1
            continue
        new = per_lang.get(term["lang"])
        if not new:
            continue
        if qa is not None and not qa.get(term["source_text"], {}).get(term["lang"], {}).get("ok"):
            counts["held_back"] += 1
            continue
        if (term["translated_text"] or "") == new:
            counts["same"] += 1
            continue
        todo.append((term, new))
    return todo, counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    lib.add_connection_args(ap)
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    ap.add_argument("--translations", default=str(WORK / "data" / "translations.json"))
    ap.add_argument("--qa", default=str(WORK / "data" / "translations_qa.json"),
                    help="Jev QA verdicts {source: {lang: {'ok': bool, 'p': float}}}; missing file = no filter")
    ap.add_argument("--views", default=str(WORK / "data" / "term_rows.json"),
                    help="term_rows.json from the extraction (gives the view ids to touch)")
    ap.add_argument("--views-csv", default=None,
                    help="take the view ids from the ir_ui_view.* rows of this proposals CSV instead")
    ap.add_argument("--backup", default=str(WORK / "terms_backup.jsonl"))
    args = ap.parse_args()

    translations = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    qa = json.loads(Path(args.qa).read_text(encoding="utf-8")) if Path(args.qa).exists() else None
    view_ids = view_ids_from_args(args.views, args.views_csv)
    client = lib.client_from_args(args)
    mode = "APPLY" if args.apply else "DRY-RUN"

    jobs = client.search_read("auto.translate.job",
                              [("model_name", "=", "ir.ui.view"), ("res_id", "in", view_ids),
                               ("field_name", "=", "arch_db")], ["id"])
    terms = client.search_read("auto.translate.term", [("job_id", "in", [j["id"] for j in jobs])],
                               ["id", "lang", "source_text", "translated_text", "state"])
    todo, counts = plan_term_writes(terms, translations, qa)
    print(f"[{mode}] views {len(view_ids)} · terms {len(terms)} · to write {len(todo)} · "
          f"already equal {counts['same']} · held back by QA {counts['held_back']} · "
          f"other sentences {counts['unknown']}")
    for t, new in todo[:8]:
        print(f"  {t['lang']}  {t['translated_text'][:60]!r}\n        -> {new[:60]!r}")
    if not args.apply:
        print("dry-run: nothing written. Re-run with --apply.")
        return 0
    written = 0
    with open(args.backup, "a", encoding="utf-8") as fh:
        for t, new in todo:
            fh.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "term_id": t["id"], "lang": t["lang"],
                                 "state": t["state"], "translated_text": t["translated_text"],
                                 "new": new}, ensure_ascii=False) + "\n")
            fh.flush()
            client.write("auto.translate.term", [t["id"]], {"translated_text": new})
            written += 1
    print(f"written: {written} (backup: {args.backup})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
