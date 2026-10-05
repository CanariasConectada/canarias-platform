#!/usr/bin/env python3
"""Workbook for the owner: merchant microsites missing homepage images, and
the strip-2 title proposals. Reads local JSON only (no database access).

Inputs: ``portadas.json`` (``inventario_portadas.py``), ``s2_estado.json``
(``propuesta_s2.py``) and ``s2_translations_qa.json`` (``qa_traducciones.py``).

Sheets:

* "Faltan imágenes": one row per merchant site missing at least one of the
  three homepage images (Hero / SEC1 / Separador backgrounds, or the company
  image fields on the dynamic template).
* "Resumen": totals, how an image is counted, and the excluded sites.
* "Listón 2 propuesto": the strip-2 title proposal per site.

An image counts as present when the es_ES page has an effective
``background-image: url(...)`` in that section whose target exists in the
database (``/web/image/<id>`` or ``/web/content/<id>`` attachment, or
``/web/image/res.company/<id>/<field>`` with the field set). A gradient or a
URL pointing at a missing attachment is not an image.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import propuesta_s2  # noqa: E402

DATA = Path("/home/odoo/Pending/jev-work/data/2026-10-05")
DEFAULT_OUT = Path("/home/odoo/microsites_imagenes_faltantes_2026-10-05.xlsx")
SLOTS = (("hero", "Portada"), ("sec1", "Sección 1"), ("separador", "Listón 2"))
SLOT_SECTION_LABEL = {"hero": "Hero", "sec1": "SEC1", "separador": "Separador"}
ZONES = {"canarias": "Canarias Conectada (sin zona de barrio)", "guanarteme": "Guanarteme",
         "tamaraceite": "Tamaraceite", "lomolosfrailes": "Lomo los Frailes"}
TEMPLATE_MIN_SITES = 3
LANG_COLUMNS = ("en_US", "de_DE", "fr_FR", "it_IT", "pl_PL", "pt_PT")


def norm(text) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def trade_name(site: dict) -> str:
    """Trade name shown on the site: ``microsite_name`` (what the dynamic
    template and the directory card show), except when it is empty or just
    repeats the legal name while the website carries another name."""
    micro, legal, web = norm(site.get("microsite_name")), norm(site["company_name"]), norm(site["website_name"])
    if not micro:
        return web or legal
    if micro.casefold() == legal.casefold() and web and web.casefold() != legal.casefold():
        return web
    return micro


def intro_text(site: dict) -> str:
    return norm(site.get("microsite_intro_title") if site.get("dynamic") else site["texts"].get("sec1_h2"))


def about_texts(site: dict) -> tuple[str, str]:
    if site.get("dynamic"):
        return norm(site.get("microsite_about_text")), norm(site.get("microsite_services_text"))
    return norm(site["texts"].get("acerca_col1")), norm(site["texts"].get("acerca_col2"))


def template_key(text: str, site: dict) -> str:
    """Text with the site's own names and zone replaced, so importer
    templates ("X nace de la pasión...", "Bienvenidos a X") collapse."""
    key = text
    names = {norm(site.get("microsite_name")), norm(site["company_name"]), norm(site["website_name"]),
             ZONES.get(site.get("commercial_zone"), ""), "Guanarteme", "Tamaraceite", "Lomo los Frailes", "tu zona"}
    for name in sorted((n for n in names if n), key=len, reverse=True):
        key = re.sub(re.escape(name), "{N}", key, flags=re.I)
    return key.casefold()


def slot_state(site: dict, slot: str) -> tuple[bool, str]:
    """(present, note) for one image slot."""
    field = {"hero": "microsite_hero_image", "sec1": "microsite_intro_image",
             "separador": "microsite_banner_image"}[slot]
    if site.get("dynamic"):
        return bool(site["company_images"].get(field)), ""
    info = site["slots"].get(slot) or {}
    if not info.get("section"):
        return False, f"la portada no tiene la sección {SLOT_SECTION_LABEL[slot]}"
    kind = info.get("kind")
    if kind == "none":
        return False, ""
    if kind in ("attachment", "company"):
        if info.get("exists"):
            return True, ""
        target = f"adjunto {info.get('attachment_id')}" if kind == "attachment" else f"campo {info.get('field')}"
        return False, f"{SLOT_SECTION_LABEL[slot]}: la URL apunta a un {target} que no existe (imagen rota)"
    return True, ""


def style_sheet(ws, widths: dict[int, int]) -> None:
    for cell in ws[1]:
        cell.font = Font(bold=True)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for col, width in widths.items():
        ws.column_dimensions[get_column_letter(col)].width = width


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--portadas", type=Path, default=DATA / "portadas.json")
    ap.add_argument("--estado", type=Path, default=DATA / "s2_estado.json")
    ap.add_argument("--qa", type=Path, default=HERE / "s2_translations_qa.json")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    all_sites = json.loads(args.portadas.read_text(encoding="utf-8"))
    sites = [s for s in all_sites if s["website_id"] not in propuesta_s2.EXCLUDED_SITES]

    # Texts shared (after name substitution) by several sites = importer template.
    template_counts = Counter()
    for site in sites:
        for text in (intro_text(site), *about_texts(site)):
            if text:
                template_counts[template_key(text, site)] += 1

    def is_template(text: str, site: dict) -> bool:
        return bool(text) and template_counts[template_key(text, site)] >= TEMPLATE_MIN_SITES

    wb = Workbook()
    ws = wb.active
    ws.title = "Faltan imágenes"
    ws.append(["Nombre Comercial", "Nombre de la Empresa", "Texto de Introducción", "Nuestra Historia",
               "Nuestros Servicios", "Faltante por Imágenes", "Segmento", "Zona", "URL", "Site ID", "Notas"])
    missing_per_slot, missing_all, complete, broken, same_names, rows_out = Counter(), 0, 0, 0, 0, 0
    for site in sites:
        states = {slot: slot_state(site, slot) for slot, _ in SLOTS}
        missing = [label for slot, label in SLOTS if not states[slot][0]]
        if not missing:
            complete += 1
            continue
        for slot, label in SLOTS:
            if not states[slot][0]:
                missing_per_slot[label] += 1
        if len(missing) == 3:
            missing_all += 1
        notes = [n for _, n in states.values() if n]
        broken += sum(1 for n in notes if "imagen rota" in n)
        intro = intro_text(site)
        about, services = about_texts(site)
        for label, text in (("Texto de Introducción", intro), ("Nuestra Historia", about),
                            ("Nuestros Servicios", services)):
            if not text:
                notes.append(f"{label}: vacío")
            elif is_template(text, site):
                notes.append(f"{label}: texto de plantilla (compartido por varios comercios)")
        if site["website_id"] in propuesta_s2.HAND_BUILT:
            notes.append("portada hecha a mano")
        if site.get("dynamic"):
            notes.append("plantilla dinámica: las imágenes van a los campos de imagen de la compañía")
        name = trade_name(site)
        hero = norm(site["texts"].get("hero_h1"))
        if not site.get("dynamic") and hero and hero.casefold() != name.casefold():
            notes.append(f"la portada muestra «{hero}» como título")
        if not site.get("category_name"):
            notes.append("sin categoría en el directorio")
        legal = norm(site["company_name"])
        same_names += name.casefold() == legal.casefold()
        ws.append([name, legal, intro, about, services, ", ".join(missing), site.get("category_name") or "",
                   ZONES.get(site.get("commercial_zone"), site.get("commercial_zone") or ""), site["domain"],
                   site["website_id"], "; ".join(notes)])
        rows_out += 1
    style_sheet(ws, {1: 28, 2: 30, 3: 40, 4: 60, 5: 60, 6: 22, 7: 30, 8: 22, 9: 40, 10: 9, 11: 60})

    estado = json.loads(args.estado.read_text(encoding="utf-8"))
    qa = json.loads(args.qa.read_text(encoding="utf-8")) if args.qa.exists() else {}
    by_id = {s["website_id"]: s for s in sites}

    rs = wb.create_sheet("Resumen")
    rs.append(["Concepto", "Valor"])
    for label, value in (
        ("Sites de comercio analizados", len(sites)),
        ("Con las 3 imágenes", complete),
        ("Con al menos una imagen faltante (filas de «Faltan imágenes»)", rows_out),
        ("Falta Portada", missing_per_slot["Portada"]),
        ("Falta Sección 1", missing_per_slot["Sección 1"]),
        ("Falta Listón 2", missing_per_slot["Listón 2"]),
        ("Faltan las 3", missing_all),
        ("Imágenes con URL rota contadas como faltantes", broken),
        ("Filas con Nombre Comercial = Nombre de la Empresa", same_names),
        ("Regla de imagen", "Presente = la página es_ES tiene background-image con URL /web/image/... o "
                           "/web/content/... cuyo destino existe en la BD; en la plantilla dinámica, el campo de "
                           "imagen de la compañía. Un degradado no cuenta."),
        ("Nombre Comercial", "res_company.microsite_name; si está vacío o repite la razón social y el website "
                             "tiene otro nombre, website.name"),
        ("Nombre de la Empresa", "res_company.name (igual a res_partner.name en los 206)"),
        ("Segmento", "res_company.category_id (res.company.category, ruta completa)"),
        ("Zona", "res_company.commercial_zone"),
        ("Datos", "BD prod (Doodba), lectura del 2026-10-05; solo lectura"),
    ):
        rs.append([label, value])
    rs.append([])
    rs.append(["Listón 2: texto actual (es_ES)", "Sites"])
    for text, count in estado["counts"]:
        rs.append([text or "(sin listón 2 en la portada)", count])
    rs.append([])
    rs.append(["Listón 2: estado de la propuesta", "Sites"])
    for status, count in Counter(s["status"] for s in estado["sites"]).most_common():
        rs.append([status, count])
    rs.append([])
    rs.append(["Site excluido", "Motivo"])
    for wid, reason in propuesta_s2.EXCLUDED_SITES.items():
        rs.append([wid, reason])
    style_sheet(rs, {1: 60, 2: 90})

    ls = wb.create_sheet("Listón 2 propuesto")
    ls.append(["Site ID", "Nombre Comercial", "Texto actual", "Propuesta ES", *LANG_COLUMNS, "Jev",
               "Estado", "Motivo"])
    for rec in sorted(estado["sites"], key=lambda r: r["site"]):
        site = by_id[rec["site"]]
        proposal = rec.get("proposal") or {}
        motivo = rec["motivo"]
        es = proposal.get("es_ES")
        if es:
            low = [lang for lang, v in qa.get(propuesta_s2.arch_text(es), {}).items() if not v.get("ok")]
            if low:
                motivo += f"; traducciones con QA Jev < 0.85 (se quedan sin escribir): {', '.join(low)}"
        ls.append([rec["site"], trade_name(site), rec["current"] or "(sin listón 2)", es or "",
                   *[proposal.get(lang, "") for lang in LANG_COLUMNS],
                   rec["fit"] if rec["fit"] is not None else "", rec["status"], motivo])
    style_sheet(ls, {1: 9, 2: 28, 3: 30, 4: 45, **{c: 40 for c in range(5, 11)}, 11: 7, 12: 11, 13: 70})

    args.out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(args.out)
    print(f"analysed {len(sites)} · complete {complete} · missing rows {rows_out} · per slot {dict(missing_per_slot)} "
          f"· all three {missing_all} · broken {broken} · same names {same_names} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
