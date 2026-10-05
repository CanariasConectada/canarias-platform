#!/usr/bin/env python3
"""Strip-2 ("Separador", "listón 2") title proposals. Read-only.

Inputs:

* ``portadas.json`` from ``inventario_portadas.py`` (current es_ES texts);
* a hand-written draft ``{site: [es, en_US, de_DE, fr_FR, it_IT, pl_PL, pt_PT]}``
  (one title per merchant, written by a person, never generated);
* the apply backup ``backup.jsonl`` (only its metadata is read) to tell our
  own ``aplicar.py`` writes apart from writes made by a person.

Outputs (``--out-dir``, default this folder):

* ``s2_texts.json``          ``{site: spanish title}`` (same shape as sec1_texts.json)
* ``s2_translations.json``   ``{arch source: {lang: translation}}`` (same shape as
  translations.json: keys and values HTML-escaped as they appear in the arch)
* ``cambios_s2.csv``         rows for ``aplicar.py``: ``Separador.h2`` of the
  homepage view plus ``res_company.microsite_banner_title``, only for sites
  whose status is "cambio"
* ``s2_estado.json``         status per site (cambio / revisión / excluido) with
  the reason and the Jev scores, consumed by ``informe_imagenes.py``

Jev (``--jev``) scores whether each title fits its business (threshold 0.85).
Without ``--jev`` no row can reach "cambio" and the CSV stays empty.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402

DATA = Path("/home/odoo/Pending/jev-work/data/2026-10-05")
LANGS = ("en_US", "de_DE", "fr_FR", "it_IT", "pl_PL", "pt_PT")
THRESHOLD = 0.85
DEFAULT_TITLE = "Consume Productos Canarios"
SCRIPT_UIDS = {1, 2}
# Our own aplicar.py run used the owner's admin account; its writes are in
# the backup log and must not count as a person editing the page.
APPLY_TS_TOLERANCE = timedelta(minutes=5)

# Sites outside the merchant scope (also listed in the workbook).
EXCLUDED_SITES = {
    1: "portal Canarias Conectada",
    12: "web de zona (Guanarteme)",
    13: "web de zona (Lomo los Frailes)",
    14: "web de zona (Tamaraceite)",
    198: "alias de administración de la compañía 1",
    223: "site de prueba (empresa1234)",
}
HAND_BUILT = {130: "portada hecha a mano (sin SEC1)", 162: "portada hecha a mano (sin SEC1)"}

# Data contradictions found while writing the titles: the title is drafted
# but a person must confirm the business before it is applied.
REVIEW_NOTES = {
    5: "categoría «Ferretería» no encaja con el texto (consultoría y formación)",
    11: "categoría «Depilación» no encaja con la academia de estudios",
    15: "categoría «Depilación» no encaja con la academia de estudios",
    16: "categoría «Depilación» no encaja con la academia de estudios",
    17: "categoría «Moda y complementos» no encaja con la papelería del texto",
    25: "nombre comercial incierto (solo «Cafeteriarubi») y categoría Pizzería",
    34: "categoría «Carpintería» no encaja con el restaurante argentino del texto",
    41: "categoría «Complementos» no encaja con la academia de pintura del texto",
    42: "categoría «Estética» no encaja con la joyería del texto",
    45: "el texto habla de «Reformas FADE» y el nombre es FAME",
    46: "website «FER Y FER» frente a «Fermo Asesores»; categoría Reformas frente a asesoría",
    51: "el nombre «FLASH PRINT» sugiere imprenta, la categoría es Alimentación y los textos son de plantilla",
    56: "los textos describen un centro de belleza y la categoría es Pilates",
    64: "SEC1 dice «Entrenamiento personalizado» y la categoría es comida para llevar",
    91: "categoría de peluquería canina; el texto habla de libros y juguetes",
    99: "website «PORTAPIZZA GUANARTEME» con zona Tamaraceite; mismo website que el site 100",
    104: "el texto menciona «Friends and Food»",
    114: "categoría «Moda y complementos» no encaja con el bazar y la lotería del texto",
    115: "website «VIVIENDO CON MICOS», categoría «Playa» y texto de boutique",
    122: "sin categoría y con textos de plantilla: no hay datos para un título específico",
    138: "nombre comercial solo como slug («joyerialucia»)",
    148: "sin categoría y con textos de plantilla: no hay datos para un título específico",
    150: "sin categoría y con textos de plantilla: no hay datos para un título específico",
    163: "nombre comercial solo como slug («mascotasbeach»)",
    166: "sin categoría, sin zona y con textos de plantilla",
    189: "sin categoría y con textos de plantilla: no hay datos para un título específico",
    190: "posible errata en el nombre («Biuty»): decisión del usuario",
    206: "subdominio de kiosco frente a categoría «Terapia» (en revisión desde 2026-09-23)",
}

STATUS_CHANGE, STATUS_REVIEW, STATUS_EXCLUDED = "cambio", "revisión", "excluido"


def parse_ts(value) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "").split("+")[0]
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def load_apply_events(path: Path, errata_backup: Path | None = None) -> dict[tuple[str, int], list[datetime]]:
    """``(model, res_id) -> [applied timestamps]`` of our own writes: the
    aplicar.py backup log and the one-off corregir_errata.py run."""
    events: dict[tuple[str, int], list[datetime]] = {}
    if errata_backup is not None and errata_backup.exists():
        import corregir_errata
        record = json.loads(errata_backup.read_text(encoding="utf-8"))
        ts = parse_ts(record.get("ts"))
        if ts is not None:
            events.setdefault((lib.MODEL_COMPANY, corregir_errata.COMPANY_ID), []).append(ts)
            if record.get("view_id"):
                events.setdefault((lib.MODEL_VIEW, int(record["view_id"])), []).append(ts)
    if not path.exists():
        return events
    for record in lib.read_backup(path):
        if record.get("event") != lib.EVENT_APPLIED:
            continue
        ts = parse_ts(record.get("ts"))
        if ts is not None:
            events.setdefault((record.get("model"), record.get("res_id")), []).append(ts)
    return events


def written_by_person(uid, write_date, model: str, res_id, events) -> bool:
    """Rule of PENDIENTE.md section 2 (write_uid not in {1, 2}), except when
    the write matches one of our own aplicar.py writes in the backup log."""
    if uid in SCRIPT_UIDS or uid is None:
        return False
    when = parse_ts(write_date)
    if when is not None:
        for ts in events.get((model, res_id), []):
            if abs(ts.replace(tzinfo=None) - when) <= APPLY_TS_TOLERANCE:
                return False
    return True


def current_strip_title(site: dict) -> str:
    """es_ES Separador heading of the page, or the company field on dynamic pages."""
    if site.get("dynamic"):
        return site.get("microsite_banner_title") or ""
    return (site.get("texts") or {}).get("separador_h2") or ""


def text_counts(sites: list[dict]) -> Counter:
    return Counter(current_strip_title(s) for s in sites)


def is_default(text: str, counts: Counter) -> bool:
    """Not filled in: empty, the importer default (any case) or shared verbatim by several sites."""
    return not text.strip() or text.casefold() == DEFAULT_TITLE.casefold() or counts[text] > 1


def arch_text(text: str) -> str:
    """How a heading text is stored in the arch (and in auto.translate.term)."""
    return html.escape(text, quote=False)


def jev_fit(site: dict, title: str) -> float:
    import jev_client
    texts = site.get("texts") or {}
    about = site.get("microsite_about_text") if site.get("dynamic") else texts.get("acerca_col1")
    services = site.get("microsite_services_text") if site.get("dynamic") else texts.get("acerca_col2")
    state = (
        "Local business microsite on Canarias Conectada (Las Palmas de Gran Canaria).\n"
        f"Trade name: {site.get('microsite_name') or site['website_name']} | Website name: {site['website_name']} | "
        f"Legal name: {site['company_name']}\n"
        f"Directory category: {site.get('category_name') or 'none'} | Commercial zone: {site.get('commercial_zone')}\n"
        f"Intro banner: {texts.get('sec1_h2') or site.get('microsite_intro_title') or '(none)'}\n"
        f"About us: {(about or '(empty)')[:500]}\nOur services: {(services or '(empty)')[:500]}\n"
        f"Proposed strip title: {title}"
    )
    q = {"fits": {"type": "noul",
                  "instructions": "Is the proposed strip title accurate and specific for this exact business, "
                                  "using only facts supported by the data above (no invented years, awards, "
                                  "superlatives or products)?",
                  "criteria": {"true": "Consistent with the name, category, zone and the merchant's own texts.",
                               "false": "Invents details, contradicts the data, or would fit another business."}}}
    ans = jev_client.decide(state, q, tag=f"s2-fit-{site['website_id']}")["answers"]
    return round(float(ans["fits"]["noul"]), 3)


def decide(site: dict, title: str | None, counts: Counter, events, fit: float | None) -> tuple[str, str]:
    wid = site["website_id"]
    current = current_strip_title(site)
    if not is_default(current, counts):
        return STATUS_EXCLUDED, "texto propio del comercio (único en la plataforma)"
    if not title:
        return STATUS_REVIEW, "sin propuesta redactada"
    reasons = []
    if written_by_person(site.get("view_write_uid"), site.get("view_write_date"), lib.MODEL_VIEW,
                         site.get("view_id"), events):
        reasons.append(f"portada editada por una persona (uid {site.get('view_write_uid')})")
    if written_by_person(site.get("company_write_uid"), site.get("company_write_date"), lib.MODEL_COMPANY,
                         site.get("company_id"), events):
        reasons.append(f"compañía editada por una persona (uid {site.get('company_write_uid')})")
    if not site.get("dynamic") and "Separador" not in (site.get("sections") or []):
        reasons.append("la portada no tiene listón 2 (sección Separador): aplicarlo exige insertar la sección")
    if wid in HAND_BUILT:
        reasons.append(HAND_BUILT[wid])
    if wid in REVIEW_NOTES:
        reasons.append(REVIEW_NOTES[wid])
    error = lib.check_strip_title(title)
    if error:
        reasons.append(f"título no válido: {error}")
    if fit is None:
        reasons.append("sin puntuación de Jev")
    elif fit < THRESHOLD:
        reasons.append(f"encaje Jev {fit:.2f} < {THRESHOLD}")
    if reasons:
        return STATUS_REVIEW, "; ".join(reasons)
    return STATUS_CHANGE, f"encaje Jev {fit:.2f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portadas", type=Path, default=DATA / "portadas.json")
    ap.add_argument("--draft", type=Path, default=HERE / "s2_borrador.json", help="hand-written titles and translations")
    ap.add_argument("--backup", type=Path, default=lib.DEFAULT_BACKUP)
    ap.add_argument("--errata-backup", type=Path, default=lib.DEFAULT_BACKUP.parent / "errata_backup.json")
    ap.add_argument("--out-dir", type=Path, default=HERE)
    ap.add_argument("--estado", type=Path, default=DATA / "s2_estado.json")
    ap.add_argument("--jev", action="store_true", help="score each title with Jev (cached)")
    args = ap.parse_args()

    sites = [s for s in json.loads(args.portadas.read_text(encoding="utf-8"))
             if s["website_id"] not in EXCLUDED_SITES]
    draft = {int(k): v for k, v in json.loads(args.draft.read_text(encoding="utf-8")).items()}
    counts = text_counts(sites)
    events = load_apply_events(args.backup, args.errata_backup)

    seen: dict[str, int] = {}
    for wid, langs in draft.items():
        key = langs[0].casefold()
        if key in seen:
            raise SystemExit(f"duplicate title for sites {seen[key]} and {wid}: {langs[0]!r}")
        seen[key] = wid

    texts, translations, estado, rows = {}, {}, [], []
    jev_error = None
    for site in sites:
        wid = site["website_id"]
        langs = draft.get(wid)
        title = langs[0] if langs else None
        fit = None
        current = current_strip_title(site)
        if title and is_default(current, counts) and args.jev and jev_error is None:
            try:
                fit = jev_fit(site, title)
            except Exception as exc:  # network, key or API failure: continue without the score
                jev_error = f"{type(exc).__name__}: {exc}"
        status, motivo = decide(site, title, counts, events, fit)
        record = {"site": wid, "current": current, "status": status, "motivo": motivo, "fit": fit,
                  "view_id": site.get("view_id"), "dynamic": site.get("dynamic"),
                  "proposal": dict(zip(("es_ES",) + LANGS, langs)) if langs and status != STATUS_EXCLUDED else None}
        estado.append(record)
        if status == STATUS_EXCLUDED or not langs:
            continue
        texts[str(wid)] = title
        translations[arch_text(title)] = {lang: arch_text(tr) for lang, tr in zip(LANGS, langs[1:])}
        if status != STATUS_CHANGE:
            continue
        common = dict(site=wid, valor_nuevo=title, confianza=f"{fit:.2f}", motivo=motivo)
        if not site.get("dynamic"):
            rows.append(dict(common, campo=f"ir_ui_view.{site['view_id']}.{lib.STRIP_SECTION}.h2",
                             valor_anterior=current))
        rows.append(dict(common, campo=f"res_company.{lib.STRIP_TITLE_FIELD}",
                         valor_anterior=site.get("microsite_banner_title") or ""))

    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "s2_texts.json").write_text(json.dumps(texts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (args.out_dir / "s2_translations.json").write_text(
        json.dumps(translations, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    with open(args.out_dir / "cambios_s2.csv", "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=lib.CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    args.estado.parent.mkdir(parents=True, exist_ok=True)
    args.estado.write_text(json.dumps({"jev_error": jev_error, "counts": counts.most_common(), "sites": estado},
                                      ensure_ascii=False, indent=1), encoding="utf-8")
    by_status = Counter(r["status"] for r in estado)
    print(f"merchant sites {len(sites)} · strip texts {dict(counts.most_common())}")
    print(f"status {dict(by_status)} · csv rows {len(rows)} · jev error {jev_error}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
