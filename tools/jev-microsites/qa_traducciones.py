#!/usr/bin/env python3
"""Jev QA of the reviewed translations before they are written.

One Decisions request per Spanish source with one ``noul`` question per
language. A translation passes when Jev gives >= 0.85. Output:
/home/odoo/Pending/jev-work/data/translations_qa.json
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_client  # noqa: E402

DATA = Path("/home/odoo/Pending/jev-work/data")
LANGS = {"en_US": "English", "de_DE": "German", "fr_FR": "French", "it_IT": "Italian",
         "pl_PL": "Polish", "pt_PT": "European Portuguese"}
THRESHOLD = 0.85


def main() -> int:
    tr = json.loads((DATA / "translations.json").read_text(encoding="utf-8"))
    qa = {}
    for i, (src, per_lang) in enumerate(tr.items()):
        state = ("Website copy for a local shop in Gran Canaria, translated from Spanish. "
                 "Markers like 【0】 are formatting placeholders and '&amp;' is an HTML ampersand; "
                 "shop, brand and place names must stay exactly as in the Spanish. "
                 "A trailing '...' marks a truncated preview.\n"
                 f"Spanish: {src}\n" + "\n".join(f"{LANGS[l]}: {per_lang[l]}" for l in LANGS))
        questions = {
            l: {"type": "noul",
                "instructions": f"Is the {LANGS[l]} version a faithful, natural and correct translation of the Spanish that keeps every shop/place name unchanged?",
                "criteria": {"true": "Same meaning, idiomatic, grammatical, names intact.",
                             "false": "Changes the meaning, is literal or ungrammatical, or alters a name."}}
            for l in LANGS}
        ans = jev_client.decide(state, questions, tag=f"qa-tr-{i}")["answers"]
        qa[src] = {l: {"p": round(float(ans[l]["noul"]), 3), "ok": float(ans[l]["noul"]) >= THRESHOLD} for l in LANGS}
    (DATA / "translations_qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=1), encoding="utf-8")
    flat = [(s, l, v["p"]) for s, d in qa.items() for l, v in d.items()]
    bad = [x for x in flat if x[2] < THRESHOLD]
    print(f"checked {len(flat)} translations · ok {len(flat) - len(bad)} · below {THRESHOLD}: {len(bad)} · cost so far {jev_client.total_cost():.4f} USD")
    for s, l, p in sorted(bad, key=lambda x: x[2])[:25]:
        print(f"  {p:.2f} {l} | {s[:70]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
