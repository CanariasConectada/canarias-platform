#!/usr/bin/env python3
"""Read-only microsite audit driven by TypeSafe Jev (OpenRouter Decisions API).

Tasks (all read-only against the production database):
  1. reviews  - per site, check that merchant reviews and local-content
                ratings are actually reachable/visible; list failures.
  2. sec1     - sites whose intro banner ("SEC1") is empty or a placeholder:
                niche via Jev + a proposed heading (max two sentences).
  3. images   - sites whose homepage sections carry no background image and
                whose company holds no microsite image either: pick the zip
                image for each section via Jev.

Sites are processed in batches of 10 (ordered by website id). Every run
rewrites the rows of the requested task/batch in cambios.csv / revision.csv
(keyed by site+campo) and refreshes PROGRESO.md, so runs are idempotent.

Usage:
  analyze.py --task 1 --batch 0        # one task, one batch
  analyze.py --task 2 --all-batches    # one task, every batch
  analyze.py --all                     # everything
"""
import argparse
import csv
import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_client  # noqa: E402

WORK = Path("/home/odoo/Pending/jev-work")
DATA = WORK / "data"
ZIP_ROOT = WORK / "zip" / "HTML_LIMPIO_WORK_FINAL" / "COMPLETOS"
DB_CONTAINER = "odoo-canariasconectada-dooba-gbb617-db-1"

CAMBIOS = HERE / "cambios.csv"
REVISION = HERE / "revision.csv"
PROGRESO = HERE / "PROGRESO.md"
ANALYSIS = DATA / "analysis.json"
PROGRESS_STATE = DATA / "progress.json"

BATCH_SIZE = 10
THRESHOLD = 0.85
SYSTEM_UIDS = {1, 2}  # 1 = OdooBot (fix scripts), 2 = RPC importer account
NON_MERCHANT_SITES = {1, 12, 13, 14, 198}  # portal, three zones, admin
TEST_SITES = {223}
PLACEHOLDER_HEADINGS = {"", "Bienvenidos a nuestro espacio", "Descubre lo que tenemos para ti"}
DEFAULT_ABOUT = "En nuestro espacio encontrarás productos y servicios seleccionados con dedicación."
SECTION_TO_FIELD = {"Hero": "microsite_hero_image", "SEC1": "microsite_intro_image", "Separador": "microsite_banner_image"}
ZIP_SLOT_TO_SECTION = {"hero": "Hero", "sec1": "SEC1", "sec2": "Separador"}
CSV_FIELDS = ["site", "campo", "valor_anterior", "valor_nuevo", "confianza", "motivo"]

NICHES = {
    "alimentacion": "Food retail: grocery, bakery, butcher, fruit shop, supermarket, delicatessen",
    "restauracion": "Bar, cafe, restaurant, pizzeria, take-away food",
    "moda": "Clothing, fashion, footwear, bags, boutique",
    "belleza": "Hairdresser, barber, beauty salon, aesthetics, nails",
    "salud_bienestar": "Health, therapy, physiotherapy, massage, wellness, herbal shop, pharmacy",
    "deporte": "Sports shop, surf, skate, bodyboard, gym, personal training",
    "informatica": "Computers, phones, electronics, tech repair",
    "hogar_ferreteria": "Hardware store, home goods, furniture, curtains, appliances",
    "automocion": "Car workshop, tyres, car glass, vehicle cleaning, e-scooters, bikes",
    "servicios_profesionales": "Consulting, insurance, legal, accounting, real estate, administration",
    "marketing_publicidad": "Marketing, advertising, printing, graphic design, photography",
    "educacion": "School, academy, language centre, nursery, tutoring",
    "arte_artesania": "Art studio, crafts, drawing and painting classes, framing",
    "animales": "Pet shop, veterinary, pet grooming, florist",
    "joyeria_regalos": "Jewellery, watches, gifts, perfumery, souvenirs",
    "loteria_kiosco": "Lottery administration, tobacco shop, kiosk, 24h convenience store",
    "costura": "Sewing atelier, clothing alterations, haberdashery",
    "otros": "None of the above",
}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def psql_json(sql: str):
    cmd = ["docker", "exec", "-i", DB_CONTAINER, "psql", "-U", "odoo", "-d", "prod",
           "-v", "ON_ERROR_STOP=1", "-At",
           "-c", "SET default_transaction_read_only = on", "-c", sql]
    out = subprocess.run(cmd, check=True, capture_output=True, text=True).stdout
    body = "\n".join(ln for ln in out.splitlines() if ln != "SET")
    return json.loads(body) if body.strip() else []


def load_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def subdomain(domain: str):
    m = re.match(r"https?://([^./]+)\.canariasconectada\.es", domain or "")
    return m.group(1) if m else None


def manual_flags(site: dict) -> dict:
    """Apply the owner's 'manual' rule to the view and the company row."""
    def later(w, c):
        return bool(w and c and w > c[:19].replace("T", " ") and (w[:16] != c[:16]))
    v_uid, c_uid = site["view_write_uid"], site["company_write_uid"]
    strict = (v_uid not in SYSTEM_UIDS) or (c_uid not in SYSTEM_UIDS) \
        or later(site["view_write_date"], site["view_create_date"]) \
        or later(site["company_write_date"], site["company_create_date"])
    effective = (v_uid not in SYSTEM_UIDS) or (c_uid not in SYSTEM_UIDS)
    return {"manual_strict": strict, "manual_effective": effective,
            "view_write_uid": v_uid, "company_write_uid": c_uid}


# --------------------------------------------------------------------------
# data loading
# --------------------------------------------------------------------------
class Context:
    def __init__(self):
        sites_doc = load_json(DATA / "sites.json")
        self.sites = sorted(sites_doc["sites"], key=lambda s: s["website_id"])
        for s in self.sites:
            s["subdomain"] = subdomain(s["domain"])
        self.by_site = {s["website_id"]: s for s in self.sites}
        self.attachments = {a["id"]: a for a in sites_doc["attachments"]}
        self.zip_map = load_json(DATA / "zip_map.json", {})
        self.zip_images = load_json(DATA / "zip_images.json", [])
        self.company_images = defaultdict(dict)
        for a in load_json(DATA / "company_images.json", []):
            self.company_images[a["company_id"]][a["res_field"]] = a
        self.sec1_texts = load_json(HERE / "sec1_texts.json", {})
        self.about_texts = load_json(HERE / "about_texts.json", {})
        self.reviews = None  # lazy

    def batches(self):
        return [self.sites[i:i + BATCH_SIZE] for i in range(0, len(self.sites), BATCH_SIZE)]

    def folders_for(self, website_id: int):
        out = [(f, v) for f, v in self.zip_map.items() if v.get("website_id") == website_id]
        out.sort(key=lambda fv: (0 if fv[1]["how"] == "exact" else 1, -float(fv[1].get("score") or 0)))
        return out

    def load_reviews(self):
        if self.reviews is not None:
            return self.reviews
        ratings = psql_json("""
            select json_agg(t) from (
              select r.id, r.res_model, r.res_id, r.res_name, r.rating, r.consumed,
                     r.moderation_status, r.feedback_moderation_status, r.feedback,
                     r.partner_id, p.name as partner_name, r.create_uid, r.create_date
              from rating_rating r left join res_partner p on p.id = r.partner_id
              order by r.id) t""") or []
        menus = psql_json("""
            select json_agg(t) from (
              select m.id, m.website_id, m.url, m.name->>'es_ES' as name, m.sequence
              from website_menu m where m.url ilike '%resenas%' order by m.website_id) t""") or []
        items = psql_json("""
            select json_agg(t) from (
              select i.id, i.name, i.state, i.is_published, i.active, i.slug,
                     t.code as type_code, t.url_slug,
                     (select array_agg(rel.website_id) from website_website_local_content_item_rel rel
                        where rel.website_local_content_item_id = i.id) as website_ids
              from website_local_content_item i
              left join website_local_content_type t on t.id = i.type_id
              where i.id in (select res_id from rating_rating where res_model='website.local.content.item')
              order by i.id) t""") or []
        self.reviews = {"ratings": ratings, "menus": menus, "items": items}
        return self.reviews


# --------------------------------------------------------------------------
# Task 1: reviews audit (deterministic + one Jev sanity check on comments)
# --------------------------------------------------------------------------
def audit_reviews(ctx: Context, site: dict) -> dict:
    rv = ctx.load_reviews()
    wid, cid = site["website_id"], site["company_id"]
    company_ratings = [r for r in rv["ratings"] if r["res_model"] == "res.company" and r["res_id"] == cid]
    visible = [r for r in company_ratings if r["consumed"] and r["moderation_status"] == "approved" and (r["rating"] or 0) >= 1]
    menus_here = [m for m in rv["menus"] if m["website_id"] == wid]
    local_menu = [m for m in menus_here if m["url"].startswith("/")]
    portal_menu = [m for m in menus_here if not m["url"].startswith("/")]
    enable = bool(site["enable_reviews"])
    failures = []

    if enable and visible and not local_menu:
        failures.append({
            "codigo": "R1", "causa": "enable_reviews=true con reseñas aprobadas pero sin entrada de menú '/resenas' en este website; "
                                    "la página existe pero no es navegable. El flag se activó sin pasar por res.company.write "
                                    "(la migración lo fijó directamente), así que _sync_reviews_website_menu nunca corrió.",
            "fix": "Ejecutar company._sync_reviews_website_menu() (o re-guardar enable_reviews desde el editor) para la compañía %d." % cid})
    if enable and not visible:
        failures.append({"codigo": "R2", "causa": "enable_reviews=true pero no hay reseñas aprobadas/consumidas: /resenas mostrará el estado vacío.",
                         "fix": "Nada que corregir; informativo."})
    if not enable and company_ratings:
        failures.append({"codigo": "R3", "causa": "Hay reseñas para la compañía pero enable_reviews=false: /resenas devuelve 404 y no se muestran.",
                         "fix": "Activar reseñas desde el editor del microsite (campo enable_reviews)."})
    if portal_menu:
        failures.append({"codigo": "R4", "causa": "El menú 'Reseñas' de este site apunta a %s, que renderiza las reseñas de la compañía del PORTAL "
                                                  "(Canarias Conectada), no las de los comercios de la zona." % portal_menu[0]["url"],
                         "fix": "Reapuntar el menú al directorio (/comercio) o eliminarlo; auto_microsite_generator/models/res_company.py fija esa URL absoluta a propósito."})
    for r in visible:
        fb = (r.get("feedback") or "").strip()
        if fb:
            ans = jev_client.decide(
                f"Merchant review on a local-commerce platform. Merchant: {site['company_name']}. Author: {r.get('partner_name')}. "
                f"Stars: {r['rating']}. Comment text: {fb!r}. Created: {r['create_date'][:10]}.",
                {"is_test": {"type": "noul", "instructions": "Is this review a test/placeholder rather than a genuine customer review?",
                             "criteria": {"true": "Text like 'test', 'hola mundo', 'prueba', lorem ipsum, or the author is the merchant/admin itself.",
                                          "false": "A genuine opinion about the merchant."}}},
                tag=f"t1-review-{r['id']}")
            p = ans["answers"]["is_test"]["noul"]
            if p >= THRESHOLD:
                failures.append({"codigo": "R5", "causa": "La reseña #%d ('%s', autor %s) parece de prueba (Jev %.2f) y es pública." % (r["id"], fb[:30], r.get("partner_name"), p),
                                 "fix": "Marcar moderation_status='rejected' o eliminar la reseña de prueba.", "jev": p})

    # local content ratings reachable from this website. Items with an empty
    # website_ids are technically served on every site, but Explora is only
    # offered (menus, landings) on the portal and the zone sites, so the
    # platform-wide findings are attached to those sites only.
    local = []
    for it in rv["items"]:
        wids = it.get("website_ids") or []
        reach = (wid in wids) or (not wids and wid in NON_MERCHANT_SITES and wid != 198)
        if not reach:
            continue
        n = sum(1 for r in rv["ratings"] if r["res_model"] == "website.local.content.item" and r["res_id"] == it["id"]
                and r["consumed"] and (r["rating"] or 0) >= 1)
        ok = it["state"] == "approved" and it["is_published"] and it["active"]
        local.append({"item_id": it["id"], "name": it["name"], "type": it["type_code"], "url": f"/explora/{it['url_slug']}/{it['slug']}",
                      "n_ratings": n, "visible": ok, "state": it["state"], "is_published": it["is_published"]})
        if n and not ok:
            failures.append({"codigo": "L1", "causa": "Contenido local '%s' (id %d, %s) tiene %d valoración(es) pero está en estado '%s' / publicado=%s: la ficha /explora no se sirve y las valoraciones no se ven." % (it["name"], it["id"], it["type_code"], n, it["state"], it["is_published"]),
                             "fix": "Aprobar y publicar el ítem (decisión editorial) o retirar las valoraciones huérfanas."})
    dup = defaultdict(list)
    for l in local:
        dup[re.sub(r"-\d+$", "", l["url"])].append(l)
    for base, group in dup.items():
        if len(group) > 1 and all(g["visible"] for g in group):
            failures.append({"codigo": "L2", "causa": "Ítems duplicados con valoraciones repartidas: %s." % ", ".join("#%d %s (%d)" % (g["item_id"], g["name"], g["n_ratings"]) for g in group),
                             "fix": "Fusionar los ítems y reasignar las valoraciones al superviviente."})
    return {"enable_reviews": enable, "reviews_total": len(company_ratings), "reviews_visible": len(visible),
            "menu_local": bool(local_menu), "menu_portal": bool(portal_menu),
            "local_items_with_ratings": local, "failures": failures,
            "estado": "FALLA" if [f for f in failures if f["codigo"] != "R2"] else "OK"}


# --------------------------------------------------------------------------
# Task 2: empty SEC1
# --------------------------------------------------------------------------
def sec1_state(site: dict):
    sec = site["sections"].get("SEC1")
    heading = " ".join(sec["headings"]).strip() if sec else None
    intro = (site["microsite_intro_title"] or "").strip()
    if sec is not None:
        empty = heading in PLACEHOLDER_HEADINGS
    else:
        empty = intro in PLACEHOLDER_HEADINGS
    return sec is not None, heading, intro, empty


def analyze_sec1(ctx: Context, site: dict):
    wid = site["website_id"]
    rows, notes = [], []
    if wid in NON_MERCHANT_SITES or wid in TEST_SITES or not site["section_order"]:
        return {"candidate": False, "reason": "no es microsite de comercio o portada vacía"}, rows, notes
    has_sec1, heading, intro, empty = sec1_state(site)
    if not empty:
        return {"candidate": False, "reason": "SEC1 con contenido", "heading": heading}, rows, notes
    flags = manual_flags(site)
    proposed = ctx.sec1_texts.get(str(wid))
    zip_info = ""
    for f, _ in ctx.folders_for(wid):
        t = ZIP_ROOT / f / "info.txt"
        if t.exists():
            zip_info = t.read_text(errors="ignore").strip().replace("\n", " | ")
    about = (site["microsite_about_text"] or "").strip()
    services = (site["microsite_services_text"] or "").strip()
    state = (
        f"Local business microsite on Canarias Conectada (Las Palmas de Gran Canaria).\n"
        f"Company name: {site['company_name']}\nWebsite: {site['domain']}\n"
        f"Directory category: {site['category_name'] or 'none'}\nCommercial zone: {site['commercial_zone']}\n"
        f"Current intro banner heading: {heading or intro or '(empty)'}\n"
        f"About text: {about[:400] or '(empty)'}\nServices text: {services[:400] or '(empty)'}\n"
        f"Hero text: {(site['sections'].get('Hero') or {}).get('text', '')[:120]}\n"
        f"Extra info from the client's zip: {zip_info or '(none)'}\n"
        f"Proposed new intro heading: {proposed or '(none)'}"
    )
    questions = {
        "niche": {"type": "choice", "instructions": "Which niche best describes this business?", "criteria": NICHES},
        "is_manual": {"type": "noul",
                      "instructions": "Was the CURRENT intro/about content written specifically for this business by its owner (hand-written), rather than a generic template or placeholder?",
                      "criteria": {"true": "Concrete details unique to this business (products, history, names, street).",
                                   "false": "Generic wording such as 'Bienvenidos a nuestro espacio' or 'En nuestro espacio encontrarás productos y servicios...' or empty."}},
    }
    if proposed:
        questions["fits"] = {"type": "noul", "instructions": "Does the proposed new intro heading fit this business accurately (no invented services, right niche, right place)?",
                             "criteria": {"true": "Consistent with the name, category, zone and any known details.",
                                          "false": "Mentions services, products or places that do not match, or contradicts the category."}}
    ans = jev_client.decide(state, questions, tag=f"t2-sec1-{wid}")["answers"]
    niche, niche_conf = ans["niche"]["choice"], float(ans["niche"].get("confidence") or 0)
    p_manual = float(ans["is_manual"]["noul"])
    p_fits = float(ans["fits"]["noul"]) if "fits" in ans else None
    rec = {"candidate": True, "has_sec1": has_sec1, "heading": heading, "intro_title": intro, "niche": niche,
           "niche_conf": niche_conf, "p_manual": p_manual, "p_fits": p_fits, "proposed": proposed, **flags}
    if proposed is None:
        notes.append(f"site {wid}: sin texto propuesto (revisar sec1_texts.json)")
        return rec, rows, notes
    conf = round(min(niche_conf, p_fits), 3)
    manual = flags["manual_effective"] or p_manual >= THRESHOLD
    motivo_base = f"nicho Jev={niche} ({niche_conf:.2f}); encaje texto={p_fits:.2f}; manual Jev={p_manual:.2f}"
    if flags["manual_strict"] and not flags["manual_effective"]:
        motivo_base += "; write_date>create_date por script propio (uid %s/%s), no manual" % (flags["view_write_uid"], flags["company_write_uid"])
    if manual:
        motivo = "MANUAL: " + ("editado por uid %s/%s" % (flags["view_write_uid"], flags["company_write_uid"]) if flags["manual_effective"] else "Jev lo considera texto propio") + "; " + motivo_base
    else:
        motivo = motivo_base
    target = "revision" if (manual or conf < THRESHOLD) else "cambios"
    rows.append({"site": wid, "campo": "res_company.microsite_intro_title", "valor_anterior": intro, "valor_nuevo": proposed,
                 "confianza": conf, "motivo": motivo, "_target": target, "_task": 2})
    if has_sec1:
        rows.append({"site": wid, "campo": f"ir_ui_view.{site['view_id']}.SEC1.h2", "valor_anterior": heading or "", "valor_nuevo": proposed,
                     "confianza": conf, "motivo": motivo, "_target": target, "_task": 2})
    else:
        rows.append({"site": wid, "campo": f"ir_ui_view.{site['view_id']}.SEC1.insert", "valor_anterior": "", "valor_nuevo": proposed,
                     "confianza": conf, "motivo": motivo + "; la portada estática no tiene sección SEC1: se inserta tras Hero con fondo degradado", "_target": target, "_task": 2})
    return rec, rows, notes


# --------------------------------------------------------------------------
# Task 3: missing images
# --------------------------------------------------------------------------
def analyze_images(ctx: Context, site: dict):
    wid, cid = site["website_id"], site["company_id"]
    rows, notes = [], []
    if wid in NON_MERCHANT_SITES or wid in TEST_SITES or "SEC1" not in site["section_order"]:
        return {"candidate": False, "reason": "no es microsite estándar de comercio"}, rows, notes
    missing = [k for k in SECTION_TO_FIELD if k in site["sections"] and site["sections"][k]["bg_attachment_id"] is None]
    if not missing:
        return {"candidate": False, "reason": "todas las secciones tienen imagen"}, rows, notes
    company_imgs = ctx.company_images.get(cid, {})
    filled_by_us = [k for k in missing if SECTION_TO_FIELD[k] in company_imgs]
    if filled_by_us:
        notes.append(f"site {wid}: la compañía ya tiene {filled_by_us} en campos de imagen; solo falta referenciarlos en la portada")
    folders = ctx.folders_for(wid)
    rec = {"candidate": True, "missing": missing, "company_has_fields": filled_by_us, "folders": [f for f, _ in folders]}
    if not folders:
        rec["reason"] = "sin carpeta en el zip"
        return rec, rows, notes
    folder, fmeta = folders[0]
    images = [f for f in ctx.zip_images if f["folder"] == folder]
    if not images:
        rec["reason"] = "carpeta sin imágenes"
        return rec, rows, notes
    flags = manual_flags(site)
    info = ""
    t = ZIP_ROOT / folder / "info.txt"
    if t.exists():
        info = t.read_text(errors="ignore").strip().replace("\n", " | ")
    listing = "\n".join(f"- file {i}: {img['path']} (subfolder '{img['slot']}', {img['size']//1024} KB)" for i, img in enumerate(images))
    state = (
        f"We must decorate the homepage of a local business microsite with images supplied by the client in a zip.\n"
        f"Site: {site['domain']} | Company: {site['company_name']} | Category: {site['category_name'] or 'none'} | Zone: {site['commercial_zone']}\n"
        f"Zip folder name: '{folder}' | folder info.txt: {info or '(none)'} | name-matching method: {fmeta['how']} (score {fmeta.get('score')})\n"
        f"Homepage sections lacking a background image: {', '.join(missing)}.\n"
        f"Section meanings: Hero = top cover banner with the business name; SEC1 = intro banner with a one-line claim (first section after the hours); Separador = closing banner ('Consume Productos Canarios') before the contact form.\n"
        f"Images in the folder:\n{listing}"
    )
    questions = {
        "folder_matches": {"type": "noul", "instructions": "Does this zip folder belong to this business/site?",
                           "criteria": {"true": "Folder name or info.txt clearly refers to the same business (name, subdomain or URL).",
                                        "false": "Names differ or refer to another business."}},
    }
    for i, img in enumerate(images):
        questions[f"img_{i}"] = {"type": "choice", "instructions": f"Which homepage section should file {i} ({img['path']}) become the background of?",
                                 "criteria": {"Hero": "Top cover banner", "SEC1": "Intro claim banner (first section)", "Separador": "Closing banner before the form", "none": "Do not use this image"}}
    ans = jev_client.decide(state, questions, tag=f"t3-img-{wid}")["answers"]
    p_match = float(ans["folder_matches"]["noul"])
    map_score = 1.0 if fmeta["how"] == "exact" else float(fmeta.get("score") or 0)
    rec.update({"folder": folder, "p_match": p_match, "map_score": map_score, "choices": {}, **flags})
    chosen = {}
    for i, img in enumerate(images):
        a = ans[f"img_{i}"]
        sec, conf = a["choice"], float(a.get("confidence") or 0)
        rec["choices"][img["path"]] = {"section": sec, "conf": conf}
        if sec in missing and (sec not in chosen or conf > chosen[sec][1]):
            chosen[sec] = (img, conf)
    for sec, (img, conf) in chosen.items():
        c = round(min(p_match, conf, map_score), 3)
        manual = flags["manual_effective"]
        motivo = f"carpeta zip '{folder}' ({fmeta['how']}, {map_score:.2f}); coincide con el site Jev={p_match:.2f}; sección elegida Jev={conf:.2f}; sección sin fondo y compañía sin imagen propia"
        if flags["manual_strict"] and not manual:
            motivo += "; write_date>create_date por script propio (uid %s/%s), no manual" % (flags["view_write_uid"], flags["company_write_uid"])
        if manual:
            motivo = "MANUAL: portada/compañía editada por uid %s/%s; " % (flags["view_write_uid"], flags["company_write_uid"]) + motivo
        target = "revision" if (manual or c < THRESHOLD) else "cambios"
        rows.append({"site": wid, "campo": f"res_company.{SECTION_TO_FIELD[sec]}", "valor_anterior": "", "valor_nuevo": img["path"],
                     "confianza": c, "motivo": motivo, "_target": target, "_task": 3})
        rows.append({"site": wid, "campo": f"ir_ui_view.{site['view_id']}.{sec}.bg", "valor_anterior": "", "valor_nuevo": img["path"],
                     "confianza": c, "motivo": motivo + "; URL final /web/image/res.company/%d/%s" % (cid, SECTION_TO_FIELD[sec]), "_target": target, "_task": 3})
    for sec in missing:
        if sec not in chosen:
            notes.append(f"site {wid}: sección {sec} sin imagen candidata en la carpeta '{folder}'")
    return rec, rows, notes


# --------------------------------------------------------------------------
# Task 4: About us / Our services
# --------------------------------------------------------------------------
TEMPLATE_PREFIXES = ("En nuestro espacio encontrarás productos", "Atención cercana y asesoramiento honesto")


def is_template(text: str) -> bool:
    t = (text or "").strip()
    return t == "" or t.startswith(TEMPLATE_PREFIXES)


def acerca_columns(view_id: int):
    """Full card-body text of each Acerca column in the es_ES arch (None if no section)."""
    import html as _html
    rows = psql_json(f"select json_build_object('a', arch_db->>'es_ES') from ir_ui_view where id = {int(view_id)}")
    arch = (rows or {}).get("a") or ""
    m = re.search(r'<section\b[^>]*data-name="Acerca".*?</section>', arch, re.S)
    if not m:
        return None
    cards = re.findall(r'<div class="card card-body bg-light">(.*?)</div>', m.group(0), re.S)
    return [re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", c))).strip() for c in cards]


def analyze_about(ctx: Context, site: dict):
    wid = site["website_id"]
    rows, notes = [], []
    if wid in NON_MERCHANT_SITES or wid in TEST_SITES or not site["section_order"]:
        return {"candidate": False, "reason": "no es microsite de comercio o portada vacía"}, rows, notes
    about, services = (site["microsite_about_text"] or "").strip(), (site["microsite_services_text"] or "").strip()
    need = {"about": is_template(about), "services": is_template(services)}
    if not any(need.values()):
        return {"candidate": False, "reason": "Sobre nosotros y Servicios con texto propio"}, rows, notes
    flags = manual_flags(site)
    proposed = ctx.about_texts.get(str(wid), {})
    cols = acerca_columns(site["view_id"]) if site["view_id"] else None
    sec1 = site["sections"].get("SEC1")
    state = (
        f"Local business microsite on Canarias Conectada (Las Palmas de Gran Canaria).\n"
        f"Company: {site['company_name']} | Website name: {site['website_name']} | Site: {site['domain']}\n"
        f"Directory category: {site['category_name'] or 'none'} | Commercial zone: {site['commercial_zone']}\n"
        f"Intro banner heading: {' '.join(sec1['headings']) if sec1 else '(none)'}\n"
        f"Current 'About us' text: {about or '(empty)'}\nCurrent 'Our services' text: {services or '(empty)'}\n"
        f"Proposed 'About us': {proposed.get('about', '(keep current)')}\nProposed 'Our services': {proposed.get('services', '(keep current)')}"
    )
    q = {
        "niche": {"type": "choice", "instructions": "Which niche best describes this business?", "criteria": NICHES},
        "is_manual": {"type": "noul",
                      "instructions": "Were the CURRENT About/Services texts written specifically for this business by its owner, rather than a generic template or left empty?",
                      "criteria": {"true": "Concrete details unique to this business.",
                                   "false": "Generic template wording ('En nuestro espacio encontrarás productos y servicios...', 'Atención cercana y asesoramiento honesto...') or empty."}},
    }
    for key, label in (("about", "About us"), ("services", "Our services")):
        if need[key] and proposed.get(key):
            q[f"fits_{key}"] = {"type": "noul", "instructions": f"Does the proposed '{label}' text fit this business accurately (no invented products, services or places; consistent with name, category, zone and banner)?",
                                "criteria": {"true": "Consistent and plausible for this exact business.", "false": "Invents details, contradicts the category or the name, or fits another business."}}
    ans = jev_client.decide(state, q, tag=f"t4-about-{wid}")["answers"]
    niche, niche_conf = ans["niche"]["choice"], float(ans["niche"].get("confidence") or 0)
    p_manual = float(ans["is_manual"]["noul"])
    fits = {k: float(ans[f"fits_{k}"]["noul"]) for k in ("about", "services") if f"fits_{k}" in ans}
    rec = {"candidate": True, "need": need, "niche": niche, "niche_conf": niche_conf, "p_manual": p_manual, "fits": fits,
           "proposed": proposed, "has_acerca": cols is not None, "n_cols": len(cols) if cols else 0,
           "current": {"about": about, "services": services}, **flags}
    manual = flags["manual_effective"] or p_manual >= THRESHOLD
    base = f"nicho Jev={niche} ({niche_conf:.2f}); manual Jev={p_manual:.2f}"
    if manual:
        base = "MANUAL: " + ("editado por uid %s/%s; " % (flags["view_write_uid"], flags["company_write_uid"]) if flags["manual_effective"] else "Jev lo considera texto propio; ") + base
    elif flags["manual_strict"]:
        base += "; write_date>create_date por script propio (uid %s/%s), no manual" % (flags["view_write_uid"], flags["company_write_uid"])
    field = {"about": "microsite_about_text", "services": "microsite_services_text"}
    col = {"about": 1, "services": 2}
    for key in ("about", "services"):
        if not need[key]:
            continue
        if not proposed.get(key):
            notes.append(f"site {wid}: sin texto propuesto para {key}")
            continue
        conf = round(min(niche_conf, fits[key]), 3)
        target = "revision" if (manual or conf < THRESHOLD) else "cambios"
        motivo = f"{base}; encaje {key}={fits[key]:.2f}"
        rows.append({"site": wid, "campo": f"res_company.{field[key]}", "valor_anterior": rec["current"][key], "valor_nuevo": proposed[key],
                     "confianza": conf, "motivo": motivo, "_target": target, "_task": 4})
        if cols is not None:
            prev = cols[col[key] - 1] if len(cols) >= col[key] else ""
            extra = "" if len(cols) >= col[key] else "; la portada no tiene esta columna: se añade"
            rows.append({"site": wid, "campo": f"ir_ui_view.{site['view_id']}.Acerca.col{col[key]}", "valor_anterior": prev, "valor_nuevo": proposed[key],
                         "confianza": conf, "motivo": motivo + extra, "_target": target, "_task": 4})
    if cols is None and all(proposed.get(k) for k in ("about", "services")):
        conf = round(min([niche_conf] + list(fits.values())), 3)
        target = "revision" if (manual or conf < THRESHOLD) else "cambios"
        payload = json.dumps({"about_title": site["microsite_about_title"] or "Sobre nosotros", "about": proposed["about"],
                              "services_title": site["microsite_services_title"] or "Nuestros servicios", "services": proposed["services"],
                              "slug": site["subdomain"] or f"site{wid}"}, ensure_ascii=False)
        rows.append({"site": wid, "campo": f"ir_ui_view.{site['view_id']}.Acerca.insert", "valor_anterior": "", "valor_nuevo": payload,
                     "confianza": conf, "motivo": base + "; la portada no tiene bloque Acerca: se inserta tras SEC1", "_target": target, "_task": 4})
    return rec, rows, notes


# --------------------------------------------------------------------------
# CSV / progress persistence
# --------------------------------------------------------------------------
def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows):
    rows = sorted(rows, key=lambda r: (int(r["site"]), r["campo"]))
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS, quoting=csv.QUOTE_ALL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in CSV_FIELDS})


def merge_rows(new_rows, sites_in_batch, task):
    """Replace, in both CSVs, the rows of these sites that belong to this task."""
    site_ids = {str(s["website_id"]) for s in sites_in_batch}
    analysis = load_json(ANALYSIS, {"sites": {}, "rows_task": {}})
    owned = analysis.setdefault("rows_task", {})  # "site|campo" -> task
    for path, target in ((CAMBIOS, "cambios"), (REVISION, "revision")):
        old = [r for r in read_csv(path) if not (r["site"] in site_ids and owned.get(f"{r['site']}|{r['campo']}") == task)]
        add = [r for r in new_rows if r["_target"] == target]
        write_csv(path, old + add)
    for r in new_rows:
        owned[f"{r['site']}|{r['campo']}"] = task
    ANALYSIS.write_text(json.dumps(analysis, ensure_ascii=False, indent=1))


def save_site_analysis(task, site_id, record):
    analysis = load_json(ANALYSIS, {"sites": {}, "rows_task": {}})
    analysis["sites"].setdefault(str(site_id), {})[f"task{task}"] = record
    ANALYSIS.write_text(json.dumps(analysis, ensure_ascii=False, indent=1))


def update_progress(ctx: Context, task, batch_idx, batch, stats, notes):
    state = load_json(PROGRESS_STATE, {"batches": {}, "notes": []})
    b = state["batches"].setdefault(str(batch_idx), {"sites": f"{batch[0]['website_id']}-{batch[-1]['website_id']}", "n": len(batch)})
    b[f"task{task}"] = {**stats, "ts": now_utc()}
    state["notes"] = [n for n in state["notes"] if not n.startswith(f"[t{task} b{batch_idx}]")] + [f"[t{task} b{batch_idx}] {n}" for n in notes]
    state["cost"] = jev_client.total_cost()
    PROGRESS_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1))
    render_progress(ctx, state)


def render_progress(ctx: Context, state):
    done_sites = {t: 0 for t in (1, 2, 3, 4)}
    lines = ["# PROGRESO — auditoría Jev de microsites (2026-09-22, trabajo nocturno)", "",
             "Solo lectura sobre la BD `prod`. Lotes de 10 sites ordenados por id de website. Jev: `typesafe/jev-1.13` vía OpenRouter Decisions API.", "",
             f"Última actualización: {now_utc()}  ·  Coste Jev acumulado: {state.get('cost', 0):.5f} USD", "",
             "| Lote | Sites | T1 reseñas | T2 sección 1 | T3 imágenes | T4 nosotros/servicios |", "|---|---|---|---|---|---|"]
    for k in sorted(state["batches"], key=int):
        b = state["batches"][k]
        cells = []
        for t in (1, 2, 3, 4):
            s = b.get(f"task{t}")
            if not s:
                cells.append("—")
                continue
            done_sites[t] += b["n"]
            if t == 1:
                cells.append(f"{s['ok']} OK / {s['fallan']} fallan")
            else:
                cells.append(f"{s['candidatos']} cand. · {s['cambios']} cambios · {s['revision']} revisión")
        lines.append(f"| {int(k):02d} | {b['sites']} | " + " | ".join(cells) + " |")
    lines += ["", f"Sites cubiertos: T1 {done_sites[1]}/{len(ctx.sites)} · T2 {done_sites[2]}/{len(ctx.sites)} · T3 {done_sites[3]}/{len(ctx.sites)} · T4 {done_sites[4]}/{len(ctx.sites)}", ""]
    if state.get("notes"):
        lines += ["## Notas por lote", ""] + [f"- {n}" for n in state["notes"]] + [""]
    PROGRESO.write_text("\n".join(lines))
    (WORK / "PROGRESO.md").write_text("\n".join(lines))


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------
def run(ctx: Context, task: int, batch_idx: int):
    batch = ctx.batches()[batch_idx]
    rows, notes = [], []
    stats = {"ok": 0, "fallan": 0, "candidatos": 0, "cambios": 0, "revision": 0}
    for site in batch:
        if task == 1:
            rec = audit_reviews(ctx, site)
            stats["ok" if rec["estado"] == "OK" else "fallan"] += 1
            r, n = [], []
        elif task == 2:
            rec, r, n = analyze_sec1(ctx, site)
        elif task == 4:
            rec, r, n = analyze_about(ctx, site)
        else:
            rec, r, n = analyze_images(ctx, site)
        if task in (2, 3, 4) and rec.get("candidate"):
            stats["candidatos"] += 1
        stats["cambios"] += sum(1 for x in r if x["_target"] == "cambios")
        stats["revision"] += sum(1 for x in r if x["_target"] == "revision")
        rows += r
        notes += n
        save_site_analysis(task, site["website_id"], rec)
    if task in (2, 3, 4):
        merge_rows(rows, batch, task)
    update_progress(ctx, task, batch_idx, batch, stats, notes)
    print(f"task {task} batch {batch_idx:02d} sites {batch[0]['website_id']}-{batch[-1]['website_id']}: {stats} cost={jev_client.total_cost():.5f}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--task", type=int, choices=(1, 2, 3, 4))
    ap.add_argument("--batch", type=int)
    ap.add_argument("--all-batches", action="store_true")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    ctx = Context()
    n_batches = len(ctx.batches())
    if args.all:
        for t in (1, 2, 3):
            for b in range(n_batches):
                run(ctx, t, b)
        return
    if args.task is None:
        ap.error("--task is required unless --all")
    if args.all_batches:
        for b in range(n_batches):
            run(ctx, args.task, b)
    elif args.batch is not None:
        run(ctx, args.task, args.batch)
    else:
        ap.error("--batch N or --all-batches required")


if __name__ == "__main__":
    main()
