#!/usr/bin/env python3
"""Read-only check that the applied homepage changes were translated.

For every homepage view touched by cambios.csv it reads ``arch_db`` in all
languages (psql with default_transaction_read_only=on) and reports, per view:

- applied:    the es_ES arch contains every new Spanish text of the CSV;
- structure:  every language has the same section order and the same
              background URLs as es_ES (Odoo rebuilds them from es_ES);
- translated: in every other language, none of the new Spanish texts is
              still present verbatim (the website_auto_translate queue
              replaced them);
- queue:      auto_translate_job rows for that view and their states.

Exit code 0 when every applied view is fully translated, 1 otherwise.
Usage: python3 validar_traducciones.py [--only-site 68,140] [--since "2026-09-23 09:00"]
"""
import argparse
import csv
import html
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
DB_CONTAINER = "odoo-canariasconectada-dooba-gbb617-db-1"
SECTION_RE = re.compile(r'<section\b[^>]*data-name="([^"]+)"[^>]*>', re.S)
BG_RE = re.compile(r"background-image:\s*url\('([^']+)'\)")
TAG_RE = re.compile(r"<[^>]+>")


def psql_json(sql: str):
    cmd = ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "odoo", "-d", "prod",
           "-v", "ON_ERROR_STOP=1", "-At", "-c", "SET default_transaction_read_only = on", "-c", sql]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    body = "\n".join(ln for ln in out.splitlines() if ln != "SET")
    return json.loads(body) if body.strip() else None


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(TAG_RE.sub(" ", text or ""))).strip()


def structure(arch: str):
    sections = []
    for m in SECTION_RE.finditer(arch or ""):
        bg = BG_RE.search(m.group(0))
        sections.append((m.group(1), bg.group(1) if bg else None))
    return sections


def new_texts_by_view(rows):
    """Spanish texts each view must show once applied (preview-length aware)."""
    texts = defaultdict(set)
    for r in rows:
        parts = r["campo"].split(".")
        if parts[0] != "ir_ui_view":
            continue
        view_id, op = int(parts[1]), ".".join(parts[2:])
        if op.endswith(".bg"):
            continue
        if op == "Acerca.insert":
            payload = json.loads(r["valor_nuevo"])
            texts[view_id].update({payload["about"], payload["services"]})
        else:
            texts[view_id].add(r["valor_nuevo"])
    return texts


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=str(HERE / "cambios.csv"))
    ap.add_argument("--only-site", default="")
    ap.add_argument("--since", default="", help="only count queue jobs written after this timestamp")
    args = ap.parse_args()
    only = {int(x) for x in args.only_site.split(",") if x.strip()}
    rows = [r for r in csv.DictReader(open(args.csv, newline="", encoding="utf-8"))
            if not only or int(r["site"]) in only]
    site_of = {}
    for r in rows:
        if r["campo"].startswith("ir_ui_view."):
            site_of[int(r["campo"].split(".")[1])] = int(r["site"])
    if not site_of:
        print("no view rows to check")
        return 0
    ids = ",".join(str(int(v)) for v in sorted(site_of))
    views = psql_json(f"select json_object_agg(id, arch_db) from ir_ui_view where id in ({ids})") or {}
    since = ""
    if args.since:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}(:\d{2})?)?", args.since):
            sys.exit("--since must look like 2026-09-23 09:00")
        since = f"and write_date >= '{args.since}'"
    jobs = psql_json(
        "select json_object_agg(res_id, s) from (select res_id, json_object_agg(state, n) s from "
        f"(select res_id, state, count(*) n from auto_translate_job where model_name='ir.ui.view' "
        f"and res_id in ({ids}) {since} group by 1, 2) t group by 1) u") or {}
    wanted = new_texts_by_view(rows)
    company = psql_json("select json_object_agg(w.id, w.company_id) from website w") or {}
    field_of = {"Hero": "microsite_hero_image", "SEC1": "microsite_intro_image", "Separador": "microsite_banner_image"}
    want_bg = defaultdict(dict)
    for r in rows:
        parts = r["campo"].split(".")
        if parts[0] == "ir_ui_view" and parts[-1] == "bg":
            cid = company[str(int(r["site"]))]
            want_bg[int(parts[1])][parts[2]] = f"/web/image/res.company/{int(cid)}/{field_of[parts[2]]}"
    total = {"ok": 0, "pendiente": 0, "no_aplicado": 0, "estructura": 0}
    print(f"{'site':>5} {'view':>6}  {'estado':<12} detalle")
    for view_id in sorted(site_of):
        arch = views.get(str(view_id)) or {}
        es = arch.get("es_ES", "")
        es_text = norm(es)
        texts = [norm(t) for t in wanted.get(view_id, set())]
        missing = [t for t in texts if t and t[:120] not in es_text]
        es_bg = dict(structure(es))
        missing_bg = [sec for sec, url in want_bg.get(view_id, {}).items() if es_bg.get(sec) != url]
        detail = []
        if missing or missing_bg:
            state = "no_aplicado"
            if missing:
                detail.append(f"{len(missing)} texto(s) aún no están en es_ES")
            if missing_bg:
                detail.append("fondo pendiente en " + ",".join(missing_bg))
        else:
            es_struct = structure(es)
            bad_struct = [lang for lang, a in arch.items() if lang != "es_ES" and structure(a) != es_struct]
            untranslated = defaultdict(int)
            for lang, a in arch.items():
                if lang == "es_ES":
                    continue
                other = norm(a)
                for t in texts:
                    if t and t[:120] in other:
                        untranslated[lang] += 1
            if bad_struct:
                state = "estructura"
                detail.append("estructura distinta en " + ",".join(sorted(bad_struct)))
            elif untranslated:
                state = "pendiente"
                detail.append("en español todavía: " + ", ".join(f"{k}({v})" for k, v in sorted(untranslated.items())))
            else:
                state = "ok"
        q = jobs.get(str(view_id)) or {}
        if q:
            detail.append("cola " + " ".join(f"{k}={v}" for k, v in sorted(q.items())))
        total[state] += 1
        print(f"{site_of[view_id]:>5} {view_id:>6}  {state:<12} {'; '.join(detail)}")
    print("\nResumen: " + " · ".join(f"{k}={v}" for k, v in total.items()))
    return 0 if total["ok"] == len(site_of) else 1


if __name__ == "__main__":
    sys.exit(main())
