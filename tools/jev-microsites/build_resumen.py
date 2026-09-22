#!/usr/bin/env python3
"""Render resumen.html from the audit outputs (analysis.json, progress.json, CSVs)."""
import csv
import datetime as dt
import html
import json
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_client  # noqa: E402

DATA = Path("/home/odoo/Pending/jev-work/data")
OUT = HERE / "resumen.html"


def esc(x):
    return html.escape("" if x is None else str(x))


def rows(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def main():
    analysis = json.loads((DATA / "analysis.json").read_text())["sites"]
    sites = {s["website_id"]: s for s in json.loads((DATA / "sites.json").read_text())["sites"]}
    progress = json.loads((DATA / "progress.json").read_text())
    cambios, revision = rows(HERE / "cambios.csv"), rows(HERE / "revision.csv")
    cost = jev_client.total_cost()
    n_calls = sum(1 for _ in (jev_client.COST_LOG.read_text().splitlines() if jev_client.COST_LOG.exists() else []))
    disk = shutil.disk_usage("/")
    zip_size = sum(p.stat().st_size for p in Path("/home/odoo/Pending/jev-work/zip").rglob("*") if p.is_file())

    t1 = {int(k): v["task1"] for k, v in analysis.items() if "task1" in v}
    t2 = {int(k): v["task2"] for k, v in analysis.items() if "task2" in v}
    t3 = {int(k): v["task3"] for k, v in analysis.items() if "task3" in v}
    fails = {k: v for k, v in t1.items() if v["estado"] == "FALLA"}

    def site_link(wid):
        s = sites[wid]
        return f'<a href="{esc(s["domain"])}" target="_blank">{wid} · {esc(s["company_name"])}</a>'

    parts = [f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Resumen auditoría Jev microsites</title>
<style>body{{font-family:system-ui,sans-serif;max-width:1200px;margin:2rem auto;padding:0 1rem;color:#222}}
table{{border-collapse:collapse;width:100%;margin:1rem 0;font-size:.9rem}}th,td{{border:1px solid #ddd;padding:.35rem .5rem;vertical-align:top;text-align:left}}
th{{background:#f4f4f4}}.ok{{color:#177245}}.bad{{color:#b00020}}.muted{{color:#666}}code{{background:#f4f4f4;padding:0 .2rem}}
.kpi{{display:inline-block;margin:.3rem 1rem .3rem 0;padding:.5rem .8rem;border:1px solid #ddd;border-radius:.4rem}}</style></head><body>
<h1>Auditoría Jev de microsites — {dt.date.today().isoformat()}</h1>
<p class="muted">Solo lectura sobre <code>prod</code>. Jev <code>typesafe/jev-1.13</code> vía OpenRouter Decisions API. Generado {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC.</p>
<div><span class="kpi"><b>{len(sites)}</b> sites analizados</span><span class="kpi"><b>{len(cambios)}</b> filas en cambios.csv ({len({r['site'] for r in cambios})} sites)</span>
<span class="kpi"><b>{len(revision)}</b> filas en revision.csv ({len({r['site'] for r in revision})} sites)</span><span class="kpi"><b>{cost:.4f} USD</b> coste Jev ({n_calls} llamadas)</span>
<span class="kpi">zip extraído: <b>{zip_size/1e6:.0f} MB</b></span><span class="kpi">disco libre: <b>{disk.free/1e9:.0f} GB</b></span></div>
"""]
    # Task 1
    parts.append(f"<h2>Tarea 1 · Reseñas — {len(t1) - len(fails)} OK / {len(fails)} con fallos</h2>")
    parts.append("<table><tr><th>Site</th><th>enable_reviews</th><th>Reseñas visibles</th><th>Menú /resenas</th><th>Fallos</th><th>Fix propuesto</th></tr>")
    for wid, v in sorted(fails.items()):
        f_html = "<br>".join(f"<b>{esc(f['codigo'])}</b> {esc(f['causa'])}" for f in v["failures"])
        x_html = "<br>".join(f"<b>{esc(f['codigo'])}</b> {esc(f['fix'])}" for f in v["failures"])
        menu = "local" if v["menu_local"] else ("→ portal" if v["menu_portal"] else "no")
        parts.append(f"<tr><td>{site_link(wid)}</td><td>{v['enable_reviews']}</td><td>{v['reviews_visible']}/{v['reviews_total']}</td><td>{menu}</td><td class='bad'>{f_html}</td><td>{x_html}</td></tr>")
    parts.append("</table>")
    parts.append(f"<p class='muted'>Los otros {len(t1) - len(fails)} sites tienen <code>enable_reviews=false</code> y ninguna reseña: no hay nada que mostrar, comportamiento correcto.</p>")
    # Task 2
    parts.append(f"<h2>Tarea 2 · Sección 1 vacía — {sum(1 for v in t2.values() if v.get('candidate'))} candidatos</h2>")
    parts.append("<table><tr><th>Site</th><th>Actual</th><th>Nicho Jev</th><th>Encaje</th><th>Manual Jev</th><th>Propuesta</th><th>Destino</th></tr>")
    for wid, v in sorted(t2.items()):
        if not v.get("candidate"):
            continue
        dest = "cambios" if any(r["site"] == str(wid) for r in cambios) else "revisión"
        cls = "ok" if dest == "cambios" else "bad"
        parts.append(f"<tr><td>{site_link(wid)}</td><td>{esc(v.get('heading') or v.get('intro_title') or '(sin sección)')}</td><td>{esc(v['niche'])} ({v['niche_conf']:.2f})</td><td>{v['p_fits']:.2f}</td><td>{v['p_manual']:.2f}</td><td>{esc(v['proposed'])}</td><td class='{cls}'>{dest}</td></tr>")
    parts.append("</table>")
    # Task 3
    cand3 = {k: v for k, v in t3.items() if v.get("candidate")}
    nofolder = sorted(k for k, v in cand3.items() if v.get("reason") == "sin carpeta en el zip")
    parts.append(f"<h2>Tarea 3 · Imágenes — {len(cand3)} sites sin fondo · {len(cand3) - len(nofolder)} con material en el zip · {len(nofolder)} sin imagen disponible</h2>")
    parts.append("<table><tr><th>Site</th><th>Secciones sin fondo</th><th>Carpeta zip</th><th>Coincide (Jev)</th><th>Elecciones</th><th>Destino</th></tr>")
    for wid, v in sorted(cand3.items()):
        if wid in nofolder:
            continue
        ch = "<br>".join(f"{esc(p)} → {c['section']} ({c['conf']:.2f})" for p, c in v.get("choices", {}).items())
        dest = "cambios" if any(r["site"] == str(wid) for r in cambios) else ("revisión" if any(r["site"] == str(wid) for r in revision) else "sin propuesta")
        cls = "ok" if dest == "cambios" else "bad"
        parts.append(f"<tr><td>{site_link(wid)}</td><td>{', '.join(v['missing'])}</td><td>{esc(v.get('folder'))}</td><td>{v.get('p_match', 0):.2f}</td><td>{ch}</td><td class='{cls}'>{dest}</td></tr>")
    parts.append("</table>")
    parts.append("<p><b>Sin imagen disponible (ni zip ni campos):</b> " + ", ".join(site_link(w) for w in nofolder) + "</p>")
    # Doubts
    parts.append("<h2>Dudas de Jev (revision.csv)</h2><table><tr><th>Site</th><th>Campo</th><th>Confianza</th><th>Motivo</th></tr>")
    for r in revision:
        parts.append(f"<tr><td>{site_link(int(r['site']))}</td><td><code>{esc(r['campo'])}</code></td><td>{esc(r['confianza'])}</td><td>{esc(r['motivo'])}</td></tr>")
    parts.append("</table>")
    # Progress
    parts.append("<h2>Lotes</h2><table><tr><th>Lote</th><th>Sites</th><th>T1</th><th>T2</th><th>T3</th></tr>")
    for k in sorted(progress["batches"], key=int):
        b = progress["batches"][k]
        cells = []
        for t in (1, 2, 3):
            s = b.get(f"task{t}", {})
            cells.append(f"{s.get('ok', 0)} OK / {s.get('fallan', 0)} fallan" if t == 1 else f"{s.get('candidatos', 0)} cand · {s.get('cambios', 0)} cambios · {s.get('revision', 0)} rev")
        parts.append(f"<tr><td>{int(k):02d}</td><td>{esc(b['sites'])}</td><td>{cells[0]}</td><td>{cells[1]}</td><td>{cells[2]}</td></tr>")
    parts.append("</table>")
    parts.append("<h2>Cómo aplicar y revertir</h2><pre>python3 aplicar.py --offline      # plan\npython3 aplicar.py                # dry-run conectado\npython3 aplicar.py --apply        # aplica en lotes de 10, backup.jsonl previo\npython3 revertir.py --apply       # restaura desde backup.jsonl</pre>")
    parts.append("<p class='muted'>Detalle de bloqueos, criterios y fixes en PENDIENTE.md.</p></body></html>")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
