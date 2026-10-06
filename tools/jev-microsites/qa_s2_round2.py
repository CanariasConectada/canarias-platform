#!/usr/bin/env python3
"""Second QA round for the strip-2 translations held back by the first one.

For every (title, language) with ok=false in ``s2_translations_qa.json``
whose term exists on a page applied from ``cambios_s2.csv``, the hand
translation is compared with the machine text stored in
``auto_translate_term`` (read-only psql through ``q.sh``):

* rules first: the hand version wins when the machine text is still Spanish,
  has lost the ":"/space after the brand, or altered the brand name;
* otherwise Jev chooses which of the two is the better rendering (the order
  of the two options is fixed per pair by a hash, not always hand first).

Outputs ``s2_translations_qa_round2.json`` (copy of the first QA with the
winning hand versions set ok=true) and ``s2_qa_round2.csv``. Nothing is
written to the database.
"""
from __future__ import annotations

import csv
import hashlib
import html
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_client  # noqa: E402

Q_SH = "/home/odoo/Pending/jev-work/q.sh"
LANG_NAMES = {"en_US": "English", "de_DE": "German", "fr_FR": "French", "it_IT": "Italian",
              "pl_PL": "Polish", "pt_PT": "European Portuguese"}
# Spanish function words that are not words of the target language.
SPANISH_MARKERS = {
    "en_US": (" en ", " y ", " para ", " del "), "de_DE": (" en ", " y ", " para ", " del "),
    "it_IT": (" en ", " y ", " para ", " del "), "pl_PL": (" en ", " y ", " para ", " del "),
    "pt_PT": (" en ", " y ", " del "), "fr_FR": (" y ", " para ", " del "),
}


def read_terms(view_ids: list[int]) -> dict:
    sql = ("select json_agg(t) from (select j.res_id, t.lang, t.source_text, t.translated_text "
           "from auto_translate_term t join auto_translate_job j on j.id = t.job_id "
           "where j.model_name = 'ir.ui.view' and j.field_name = 'arch_db' "
           f"and j.res_id in ({','.join(str(int(v)) for v in view_ids)})) t")
    out = subprocess.run([Q_SH, "-At", sql], capture_output=True, text=True, check=True).stdout
    rows = json.loads("\n".join(ln for ln in out.splitlines() if ln != "SET") or "[]") or []
    index = {}
    for row in rows:
        index.setdefault((row["res_id"], row["lang"], row["source_text"]), row["translated_text"] or "")
    return index


def brand_of(source: str) -> tuple[str, str]:
    """(brand, separator) of a title such as "Brand: text" or "Brand, text"."""
    cut = [i for i in (source.find(":"), source.find(",")) if i > 0]
    if not cut:
        return "", ""
    i = min(cut)
    return source[:i], source[i]


def rule_verdict(source: str, machine: str, hand: str, lang: str) -> str:
    """Reason why the hand version wins outright, or ``""``."""
    src, mach, mine = (html.unescape(t) for t in (source, machine, hand))
    if mach.strip() == src.strip():
        return "machine text is still the Spanish source"
    padded, padded_mine = f" {mach} ", f" {mine} "
    for marker in SPANISH_MARKERS[lang]:
        if marker in padded and marker not in padded_mine:
            return f"machine text still has Spanish words ({marker.strip()!r})"
    brand, sep = brand_of(src)
    if brand:
        if not mach.startswith(brand):
            return f"machine text altered the brand {brand!r}"
        rest = mach[len(brand):]
        if sep == ":" and not (rest.startswith(": ") or rest.startswith(" : ")):
            return "machine text lost the colon/space after the brand"
    return ""


def jev_choice(source: str, hand: str, machine: str, lang: str) -> tuple[str, float]:
    swap = int(hashlib.sha256(f"{source}|{lang}".encode()).hexdigest(), 16) % 2 == 1
    a, b = (machine, hand) if swap else (hand, machine)
    state = (f"Strip title of a local shop's website in Gran Canaria, translated from Spanish into {LANG_NAMES[lang]}. "
             "'&amp;' is an HTML ampersand. Shop, brand and place names must stay exactly as in the Spanish.\n"
             f"Spanish: {source}\nOption A: {a}\nOption B: {b}")
    q = {"better": {"type": "choice",
                    "instructions": f"Which of the two is the better {LANG_NAMES[lang]} rendering of this Spanish "
                                    "title? Brand names must stay verbatim.",
                    "criteria": {"A": "Option A is more faithful, natural and correct, names intact.",
                                 "B": "Option B is more faithful, natural and correct, names intact."}}}
    ans = jev_client.decide(state, q, tag=f"s2-qa2-{lang}")["answers"]["better"]
    choice = ans["choice"]
    hand_key = "B" if swap else "A"
    return ("hand" if choice == hand_key else "machine"), round(float(ans.get("confidence") or 0), 3)


def main() -> int:
    qa = json.loads((HERE / "s2_translations_qa.json").read_text(encoding="utf-8"))
    translations = json.loads((HERE / "s2_translations.json").read_text(encoding="utf-8"))
    with open(HERE / "cambios_s2.csv", encoding="utf-8") as fh:
        views = {int(r["campo"].split(".")[1]): (int(r["site"]), html.escape(r["valor_nuevo"], quote=False))
                 for r in csv.DictReader(fh) if ".Separador.h2" in r["campo"]}
    terms = read_terms(sorted(views))
    out_qa = json.loads(json.dumps(qa))
    report = []
    for view_id, (site, source) in sorted(views.items()):
        for lang, verdict in qa[source].items():
            if verdict["ok"]:
                continue
            machine = terms.get((view_id, lang, source))
            hand = translations[source][lang]
            if machine is None:
                report.append([site, view_id, lang, "", hand, "machine", "term not found on the page", ""])
                continue
            reason = rule_verdict(source, machine, hand, lang)
            if reason:
                winner, conf = "hand", ""
            else:
                winner, conf = jev_choice(source, hand, machine, lang)
                reason = f"Jev choice ({conf:.2f})"
            if winner == "hand":
                out_qa[source][lang] = dict(verdict, ok=True, round2=reason)
            report.append([site, view_id, lang, html.unescape(machine), html.unescape(hand),
                           "ours" if winner == "hand" else "machine", reason, verdict["p"]])
    (HERE / "s2_translations_qa_round2.json").write_text(json.dumps(out_qa, ensure_ascii=False, indent=1),
                                                         encoding="utf-8")
    with open(HERE / "s2_qa_round2.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh, quoting=csv.QUOTE_ALL)
        writer.writerow(["site", "view_id", "lang", "machine", "hand", "verdict", "reason", "qa1_p"])
        writer.writerows(report)
    wins = sum(1 for r in report if r[5] == "ours")
    print(f"held back {len(report)} · ours {wins} · machine {len(report) - wins} · "
          f"jev cost so far {jev_client.total_cost():.4f} USD")
    return 0


if __name__ == "__main__":
    sys.exit(main())
