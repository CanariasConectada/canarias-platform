#!/usr/bin/env python3
"""Protect the commerce names used in the new microsite texts and re-translate.

The website_auto_translate engine translated or mangled some commerce names
written in the 2026-09-23 texts (e.g. "El Tucán 24H" -> "The Tucan 24H",
"M&G Moda" -> "M&G Fashion"). The module's own remedy is:

1. add the exact spelling to ``auto.translate.glossary`` (never translated);
2. call ``auto.translate.job.action_translate_again`` on the affected pages,
   which re-queues them without touching sentences corrected by hand.

Names containing "&" are matched against the page HTML, where the ampersand is
stored as "&amp;", so the glossary entry must use that form.

Dry-run by default; ``--apply`` writes. Run through con_credenciales.sh.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402

NOTE = "Commerce/place name in the 2026-09-23 microsite texts (tools/jev-microsites)"

# website id -> glossary terms to protect on that site's homepage
TERMS = {
    39: ["El Tucán 24H"],
    175: ["Peluquería Soraya Godoy"],
    178: ["M&amp;G Moda"],
    188: ["Muévete Training Club"],
    190: ["Profesional Beauty by Estefanía"],
    197: ["Óptica 1500", "La Aldea de San Nicolás"],
    207: ["La Cage aux Folles"],
}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    lib.add_connection_args(ap)
    ap.add_argument("--apply", action="store_true", help="write (default: dry-run)")
    ap.add_argument("--plan", help="JSON file {'glossary': [terms], 'jobs': [job ids]} instead of the built-in list")
    args = ap.parse_args()
    if args.plan:
        return run_plan(args)
    client = lib.client_from_args(args)
    mode = "APPLY" if args.apply else "DRY-RUN"

    # 1. Glossary entries (skip names that already exist, case-insensitively).
    to_create = []
    for site, terms in TERMS.items():
        for term in terms:
            # The database has unaccent, so =ilike also returns "EL TUCAN 24H"
            # for "El Tucán 24H"; the engine's guard is accent-sensitive, so
            # only an exact (case-insensitive) spelling counts as existing.
            candidates = client.search_read("auto.translate.glossary",
                                            [("name", "=ilike", term), ("lang", "=", False)], ["id", "name"])
            existing = [c for c in candidates if c["name"].casefold() == term.casefold()]
            if existing:
                print(f"[{mode}] glossary  site {site:>3}  EXISTS   {term!r} (id {existing[0]['id']})")
            else:
                print(f"[{mode}] glossary  site {site:>3}  CREATE   {term!r}")
                to_create.append({"name": term, "note": NOTE})
    if args.apply and to_create:
        ids = client.execute_kw("auto.translate.glossary", "create", [to_create])
        print(f"created glossary ids: {ids}")

    # 2. Re-queue the homepage translation jobs of those sites.
    pages = client.search_read("website.page", [("website_id", "in", list(TERMS)), ("url", "=", "/")],
                               ["website_id", "view_id"])
    view_ids = sorted({p["view_id"][0] for p in pages if p.get("view_id")})
    jobs = client.search_read("auto.translate.job",
                              [("model_name", "=", "ir.ui.view"), ("res_id", "in", view_ids),
                               ("field_name", "=", "arch_db")],
                              ["id", "res_id", "lang", "state"])
    redo = [j for j in jobs if j["state"] != "locked"]
    locked = [j for j in jobs if j["state"] == "locked"]
    print(f"[{mode}] jobs: {len(redo)} to translate again on views {view_ids}; {len(locked)} locked (left alone)")
    if args.apply and redo:
        n = client.execute_kw("auto.translate.job", "action_translate_again", [[j["id"] for j in redo]])
        print(f"re-queued: {n}")
    if not args.apply:
        print("dry-run: nothing written. Re-run with --apply.")
    return 0


def run_plan(args) -> int:
    """Platform-wide variant: glossary terms and job ids come from a plan file."""
    import json
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    client = lib.client_from_args(args)
    mode = "APPLY" if args.apply else "DRY-RUN"
    to_create = []
    for term in plan["glossary"]:
        candidates = client.search_read("auto.translate.glossary",
                                        [("name", "=ilike", term), ("lang", "=", False)], ["id", "name"])
        if any(c["name"].casefold() == term.casefold() for c in candidates):
            print(f"[{mode}] glossary EXISTS {term!r}")
        else:
            print(f"[{mode}] glossary CREATE {term!r}")
            to_create.append({"name": term, "note": "Commerce name missing from the glossary (tools/jev-microsites, 2026-09-23)"})
    job_ids = [int(j) for j in plan["jobs"]]
    jobs = client.search_read("auto.translate.job", [("id", "in", job_ids)], ["id", "state", "model_name"])
    redo = [j["id"] for j in jobs if j["state"] != "locked" and j["model_name"] == "ir.ui.view"]
    print(f"[{mode}] jobs: {len(redo)} to translate again ({len(job_ids) - len(redo)} skipped: locked or missing)")
    if args.apply:
        if to_create:
            print("created glossary ids:", client.execute_kw("auto.translate.glossary", "create", [to_create]))
        if redo:
            print("re-queued:", client.execute_kw("auto.translate.job", "action_translate_again", [redo]))
    else:
        print("dry-run: nothing written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
