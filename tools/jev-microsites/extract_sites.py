#!/usr/bin/env python3
"""Read-only extraction of every microsite's homepage into data/sites.json.

Runs psql inside the Doodba Postgres container with
default_transaction_read_only=on. Nothing is written to the database.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

DB_CONTAINER = "odoo-canariasconectada-dooba-gbb617-db-1"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/odoo/Pending/jev-work/data/sites.json")

SQL = r"""
select json_agg(t) from (
  select w.id as website_id, w.name as website_name, w.domain, w.company_id,
         c.name as company_name, c.category_id, cat.name as category_name,
         c.enable_reviews, c.microsite_intro_title, c.microsite_banner_title,
         c.microsite_about_title, c.microsite_about_text,
         c.microsite_services_title, c.microsite_services_text,
         c.microsite_subdomain, c.commercial_zone, c.microsite_homepage_page_id,
         c.create_uid as company_create_uid, c.write_uid as company_write_uid,
         c.create_date as company_create_date, c.write_date as company_write_date,
         p.id as page_id, p.url as page_url,
         v.id as view_id, v.key as view_key, v.active as view_active,
         v.create_uid as view_create_uid, v.write_uid as view_write_uid,
         v.create_date as view_create_date, v.write_date as view_write_date,
         v.arch_db->>'es_ES' as arch_es
  from website w
  join res_company c on c.id = w.company_id
  left join res_company_category cat on cat.id = c.category_id
  left join website_page p on p.website_id = w.id and p.url = '/'
  left join ir_ui_view v on v.id = p.view_id
  order by w.id
) t
"""

ATT_SQL = r"""
select json_agg(t) from (
  select a.id, a.name, a.res_model, a.res_id, a.res_field, a.mimetype,
         a.file_size, a.create_uid, a.write_uid, a.create_date, a.write_date,
         a.public, a.website_id, a.checksum
  from ir_attachment a where a.id = any(array[%s])
) t
"""


def psql(sql: str) -> str:
    cmd = [
        "docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "odoo", "-d", "prod",
        "-v", "ON_ERROR_STOP=1", "-At",
        "-c", "SET default_transaction_read_only = on",
        "-c", sql,
    ]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    lines = [ln for ln in out.splitlines() if ln != "SET"]
    return "\n".join(lines)


SECTION_RE = re.compile(r'<section\b[^>]*data-name="([^"]+)"[^>]*>.*?</section>', re.S)
BG_RE = re.compile(r"background-image:\s*url\('([^']+)'\)")
ATT_ID_RE = re.compile(r"/web/image/(?:ir\.attachment/)?(\d+)")
TAG_RE = re.compile(r"<[^>]+>")


def text_of(html: str) -> str:
    return re.sub(r"\s+", " ", TAG_RE.sub(" ", html)).strip()


def parse_sections(arch: str) -> dict:
    result = {}
    for m in SECTION_RE.finditer(arch or ""):
        name = m.group(1)
        html = m.group(0)
        head = re.match(r"<section\b[^>]*>", html).group(0)
        bg = BG_RE.search(head)
        bg_url = bg.group(1) if bg else None
        att = ATT_ID_RE.search(bg_url) if bg_url else None
        imgs = [(i, (ATT_ID_RE.search(i) or [None, None])[1]) for i in re.findall(r'<img[^>]*src="([^"]+)"', html)]
        headings = [text_of(h) for h in re.findall(r"<h[1-6][^>]*>(.*?)</h[1-6]>", html, re.S)]
        paras = [text_of(p) for p in re.findall(r"<(?:p|small|div class=\"card card-body[^\"]*\")[^>]*>(.*?)</(?:p|small|div)>", html, re.S)]
        paras = [p for p in paras if p]
        result[name] = {
            "bg_url": bg_url,
            "bg_attachment_id": int(att.group(1)) if att else None,
            "img_attachment_ids": [int(a) for _, a in imgs if a],
            "img_srcs": [i for i, _ in imgs],
            "headings": headings,
            "paragraphs": paras,
            "text": text_of(html),
            "html_len": len(html),
        }
    return result


def main():
    rows = json.loads(psql(SQL) or "[]")
    att_ids = set()
    for r in rows:
        r["sections"] = parse_sections(r.pop("arch_es") or "")
        r["section_order"] = list(r["sections"].keys())
        for s in r["sections"].values():
            if s["bg_attachment_id"]:
                att_ids.add(s["bg_attachment_id"])
            att_ids.update(s["img_attachment_ids"])
    atts = json.loads(psql(ATT_SQL % ",".join(str(i) for i in sorted(att_ids))) or "[]") if att_ids else []
    OUT.write_text(json.dumps({"sites": rows, "attachments": atts}, ensure_ascii=False, indent=1))
    print(f"sites={len(rows)} attachments={len(atts)} -> {OUT}")


if __name__ == "__main__":
    main()
