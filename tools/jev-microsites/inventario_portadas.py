#!/usr/bin/env python3
"""Read-only inventory of every merchant homepage: names, texts and images.

Runs psql inside the Doodba Postgres container with
default_transaction_read_only=on (same access path as ``extract_sites.py``).
Nothing is written to the database. Output: one JSON file with a record per
website, consumed by ``informe_imagenes.py`` and ``propuesta_s2.py``.

Per site it records the three homepage image slots (Hero, SEC1, Separador)
as seen in the es_ES arch, the texts of SEC1, Acerca and Separador, and the
company fields that the dynamic template reads instead. Background URLs are
checked against ``ir_attachment`` so a dangling reference is not counted as
an image.

Usage: python3 inventario_portadas.py [OUT.json]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402

DB_CONTAINER = "odoo-canariasconectada-dooba-gbb617-db-1"
DEFAULT_OUT = Path("/home/odoo/Pending/jev-work/data/2026-10-05/portadas.json")

# Slot -> section names that play that role (hand-built pages call the
# cover "Portada" or "Cover").
SLOT_SECTIONS = {
    "hero": ("Hero", "Portada", "Cover"),
    "sec1": ("SEC1",),
    "separador": ("Separador",),
}
SLOT_IMAGE_FIELD = {
    "hero": "microsite_hero_image",
    "sec1": "microsite_intro_image",
    "separador": "microsite_banner_image",
}
DYNAMIC_KEY_PREFIX = "partner_microsite_manager.microsite_homepage_"

SITES_SQL = r"""
select json_agg(t) from (
  select w.id as website_id, w.name as website_name, w.domain, w.company_id,
         c.name as company_name, c.microsite_name, c.partner_id,
         p.name as partner_name, p.vat as partner_vat,
         c.commercial_zone, c.category_id, cat.complete_name as category_name,
         c.microsite_intro_title, c.microsite_banner_title,
         c.microsite_about_text, c.microsite_services_text,
         c.microsite_subdomain,
         c.create_uid as company_create_uid, c.write_uid as company_write_uid,
         c.write_date as company_write_date,
         pg.id as page_id, v.id as view_id, v.key as view_key,
         v.create_uid as view_create_uid, v.write_uid as view_write_uid,
         v.write_date as view_write_date,
         v.arch_db->>'es_ES' as arch_es,
         (select json_object_agg(a.res_field, coalesce(a.file_size, -1)) from ir_attachment a
           where a.res_model = 'res.company' and a.res_id = c.id
             and a.res_field in ('microsite_hero_image', 'microsite_intro_image',
                                 'microsite_banner_image')) as company_images
  from website w
  join res_company c on c.id = w.company_id
  join res_partner p on p.id = c.partner_id
  left join res_company_category cat on cat.id = c.category_id
  left join website_page pg on pg.website_id = w.id and pg.url = '/'
  left join ir_ui_view v on v.id = pg.view_id
  order by w.id
) t
"""

ATT_SQL = "select json_agg(json_build_object('id', id, 'size', file_size)) from ir_attachment where id = any(array[%s])"

_ATT_URL_RE = re.compile(r"^/web/(?:image|content)/(?:ir\.attachment/)?(\d+)(?:[/?_-]|$)")
_COMPANY_URL_RE = re.compile(r"^/web/(?:image|content)/res\.company/(\d+)/(\w+)")
_IMAGE_URL_RE = re.compile(r"^/web/(?:image|content)/")


def psql(sql: str) -> str:
    cmd = ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "odoo", "-d", "prod",
           "-v", "ON_ERROR_STOP=1", "-At",
           "-c", "SET default_transaction_read_only = on", "-c", sql]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    return "\n".join(ln for ln in out.splitlines() if ln != "SET")


def find_slot_section(arch: str, slot: str) -> str | None:
    """Name of the first section present in the arch for that slot."""
    for name in SLOT_SECTIONS[slot]:
        try:
            if lib.find_section(arch, name):
                return name
        except lib.ArchError:
            continue
    return None


def classify_bg(url: str | None) -> dict:
    """Shape of a background URL: ``kind`` is ``none``, ``attachment``
    (``/web/image|content/<id>``), ``company`` (``/web/image/res.company/..``)
    or ``other`` (any non /web/ URL, e.g. an external picture)."""
    if not url:
        return {"kind": "none"}
    m = _COMPANY_URL_RE.match(url)
    if m:
        return {"kind": "company", "company_id": int(m.group(1)), "field": m.group(2)}
    m = _ATT_URL_RE.match(url)
    if m:
        return {"kind": "attachment", "attachment_id": int(m.group(1))}
    if _IMAGE_URL_RE.match(url):
        return {"kind": "other_web"}
    return {"kind": "other"}


def section_texts(arch: str) -> dict:
    """Texts the image generator and the strip-2 proposal need (es_ES)."""
    out = {"hero_h1": None, "sec1_h2": None, "separador_h2": None, "acerca_col1": None, "acerca_col2": None}
    hero = find_slot_section(arch, "hero")
    if hero:
        section = lib.find_section(arch, hero)
        m = re.search(r"<h1\b[^>]*>(.*?)</h1\s*>", section.group(), re.S)
        out["hero_h1"] = lib.normalize_text(lib._TAG_RE.sub("", m.group(1))) if m else None
    for key, name in (("sec1_h2", "SEC1"), ("separador_h2", "Separador")):
        try:
            out[key] = lib.extract_section_h2(arch, name)
        except lib.SectionNotFound:
            pass
    try:
        if lib.find_section(arch, lib.ACERCA_SECTION):
            out["acerca_col1"] = lib.normalize_text(lib.extract_acerca_column(arch, 1))
            out["acerca_col2"] = lib.normalize_text(lib.extract_acerca_column(arch, 2))
    except lib.ArchError as exc:
        out["acerca_error"] = str(exc)
    return out


def slot_images(arch: str) -> dict:
    slots = {}
    for slot in SLOT_SECTIONS:
        name = find_slot_section(arch, slot)
        info = {"section": name, "url": None}
        if name:
            try:
                info["url"] = lib.extract_section_bg(arch, name)
            except lib.ArchError as exc:
                info["error"] = str(exc)
        info.update(classify_bg(info["url"]))
        slots[slot] = info
    return slots


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    rows = json.loads(psql(SITES_SQL) or "[]")
    att_ids: set[int] = set()
    for row in rows:
        arch = row.pop("arch_es") or ""
        row["dynamic"] = bool(row.get("view_key") and row["view_key"].startswith(DYNAMIC_KEY_PREFIX))
        row["company_images"] = row.get("company_images") or {}
        row["texts"] = section_texts(arch) if arch else {}
        row["slots"] = slot_images(arch) if arch else {}
        row["sections"] = re.findall(r'<section\b[^>]*\sdata-name="([^"]+)"', arch)
        for info in row["slots"].values():
            if info.get("kind") == "attachment":
                att_ids.add(info["attachment_id"])
    if not all(isinstance(i, int) for i in att_ids):
        raise TypeError("attachment ids must be ints")
    existing = {}
    if att_ids:
        found = json.loads(psql(ATT_SQL % ",".join(map(str, sorted(att_ids)))) or "[]") or []
        existing = {a["id"]: a["size"] for a in found}
    for row in rows:
        for info in row["slots"].values():
            if info.get("kind") == "attachment":
                info["exists"] = info["attachment_id"] in existing
            elif info.get("kind") == "company":
                same = info["company_id"] == row["company_id"]
                info["exists"] = same and bool(row["company_images"].get(info["field"]))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"sites={len(rows)} attachments checked={len(att_ids)} found={len(existing)} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
