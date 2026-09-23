#!/usr/bin/env python3
"""Fix the "Estefaníaa" typo of website 190 (Profesional Biuty by Estefanía).

1. res.company 192 ``microsite_name``: "…Estefaníaa" -> "…Estefanía".
2. Homepage view of website 190: the Hero heading, written in es_ES only
   (Odoo regenerates the other languages; the glossary keeps the name).
3. Glossary entry holding the misspelt name: removed (the correct spelling
   already has its own entry).

Dry-run by default; ``--apply`` writes. The full homepage arch (every
language) is saved to --backup before the write. Run via con_credenciales.sh.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402

WEBSITE_ID = 190
COMPANY_ID = 192
WRONG = "Estefaníaa"
RIGHT = "Estefanía"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    lib.add_connection_args(ap)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--backup", default="/home/odoo/Pending/jev-work/errata_backup.json")
    args = ap.parse_args()
    client = lib.client_from_args(args)
    mode = "APPLY" if args.apply else "DRY-RUN"

    company = client.read("res.company", [COMPANY_ID], ["microsite_name"])[0]
    name = company["microsite_name"] or ""
    new_name = name.replace(WRONG, RIGHT)
    print(f"[{mode}] res.company {COMPANY_ID} microsite_name: {name!r} -> {new_name!r}"
          + ("" if name != new_name else "  (nothing to do)"))

    page = client.search_read("website.page", [("website_id", "=", WEBSITE_ID), ("url", "=", "/")], ["view_id"])
    view_id = page[0]["view_id"][0]
    langs = [l["code"] for l in client.search_read("res.lang", [("active", "=", True)], ["code"])]
    arches = {l: client.read("ir.ui.view", [view_id], ["arch_db"], {"lang": l})[0]["arch_db"] for l in langs}
    es = arches["es_ES"]
    count = es.count(WRONG)
    print(f"[{mode}] ir.ui.view {view_id} (es_ES): {count} occurrence(s) of {WRONG!r}")

    gloss = client.search_read("auto.translate.glossary", [("name", "=", f"Profesional Biuty by {WRONG}")], ["id", "name"])
    print(f"[{mode}] glossary to remove: {[g['id'] for g in gloss]}")

    if not args.apply:
        print("dry-run: nothing written. Re-run with --apply.")
        return 0
    Path(args.backup).write_text(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "view_id": view_id,
                                             "arch_db": arches, "microsite_name": name}, ensure_ascii=False),
                                 encoding="utf-8")
    if name != new_name:
        client.write("res.company", [COMPANY_ID], {"microsite_name": new_name})
    if count:
        client.write("ir.ui.view", [view_id], {"arch_db": es.replace(WRONG, RIGHT)}, {"lang": "es_ES"})
    if gloss:
        client.execute_kw("auto.translate.glossary", "unlink", [[g["id"] for g in gloss]])
    print(f"done (backup: {args.backup})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
