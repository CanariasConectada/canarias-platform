#!/usr/bin/env python3
"""Replace the machine translation of the new microsite sentences by reviewed ones.

Uses the website_auto_translate correction path: writing ``translated_text``
on an ``auto.translate.term`` applies the sentence to the page in that language
and locks it, so the machine never overwrites it again (the module's
documented behaviour for hand corrections).

Input: a JSON file {spanish_source_text: {lang: translation}}; only rows whose
Jev QA verdict is "ok" in the optional --qa file are written.

Dry-run by default; ``--apply`` writes. Every previous value is appended to
--backup (JSON lines) before its write. Run through con_credenciales.sh.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402

WORK = Path("/home/odoo/Pending/jev-work")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    lib.add_connection_args(ap)
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    ap.add_argument("--translations", default=str(WORK / "data" / "translations.json"))
    ap.add_argument("--qa", default=str(WORK / "data" / "translations_qa.json"),
                    help="Jev QA verdicts {source: {lang: {'ok': bool, 'p': float}}}; missing file = no filter")
    ap.add_argument("--views", default=str(WORK / "data" / "term_rows.json"),
                    help="term_rows.json from the extraction (gives the view ids to touch)")
    ap.add_argument("--backup", default=str(WORK / "terms_backup.jsonl"))
    args = ap.parse_args()

    translations = json.loads(Path(args.translations).read_text(encoding="utf-8"))
    qa = json.loads(Path(args.qa).read_text(encoding="utf-8")) if Path(args.qa).exists() else None
    view_ids = sorted({int(r["v"]) for r in json.loads(Path(args.views).read_text(encoding="utf-8"))})
    client = lib.client_from_args(args)
    mode = "APPLY" if args.apply else "DRY-RUN"

    jobs = client.search_read("auto.translate.job",
                              [("model_name", "=", "ir.ui.view"), ("res_id", "in", view_ids),
                               ("field_name", "=", "arch_db")], ["id"])
    terms = client.search_read("auto.translate.term", [("job_id", "in", [j["id"] for j in jobs])],
                               ["id", "lang", "source_text", "translated_text", "state"])
    todo, skipped_qa, same, unknown = [], 0, 0, 0
    for t in terms:
        per_lang = translations.get(t["source_text"])
        if not per_lang:
            unknown += 1
            continue
        new = per_lang.get(t["lang"])
        if not new:
            continue
        if qa is not None and not qa.get(t["source_text"], {}).get(t["lang"], {}).get("ok"):
            skipped_qa += 1
            continue
        if (t["translated_text"] or "") == new:
            same += 1
            continue
        todo.append((t, new))
    print(f"[{mode}] views {len(view_ids)} · terms {len(terms)} · to write {len(todo)} · "
          f"already equal {same} · held back by QA {skipped_qa} · other sentences {unknown}")
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
