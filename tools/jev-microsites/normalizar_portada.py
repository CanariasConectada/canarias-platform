#!/usr/bin/env python3
"""Dry run: rebuild deviating homepages onto the standard skeleton (offline).

Reads the current ``arch_db`` jsonb of every site and of the reference view
(``arch_before_<view_id>.json`` files, dumped read-only from the database),
renders the standard skeleton per language with ``jev_rebuild_lib``, validates
the result (``jev_rebuild_check``), proves the term extraction against Odoo's
own ``xml_translate`` when the Odoo source tree is importable, and writes:

* ``arch_after_<view_id>.json`` next to the inputs (same jsonb shape);
* a proposals CSV (``--csv-out``) in the ``aplicar.py`` row format with one
  ``ir_ui_view.<view_id>.Homepage.rebuild`` row per site, ``valor_anterior``
  the current section list and ``valor_nuevo`` the arch file name;
* a report (``--report``) with before/after sections, carried-over texts per
  language and the flags (sections omitted, pictures missing...).

Nothing talks to Odoo. The owner applies the CSV later with::

    python3 aplicar.py --csv cambios_portadas.csv --offline          # checks
    python3 aplicar.py --csv cambios_portadas.csv --login ... --apply --yes

Sites come from ``--sites`` (``normalizar_sitios.csv``: ``site`` website id,
``slug``, ``company_id``, ``view_id`` and the ``has_about/has_hero/has_intro/
has_banner`` 0/1 columns read from the database for the flags).
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import jev_apply_lib as lib  # noqa: E402
import jev_rebuild_check as check  # noqa: E402
import jev_rebuild_lib as rb  # noqa: E402
import jev_rebuild_terms as terms  # noqa: E402

DEFAULT_SITES = HERE / "normalizar_sitios.csv"
DEFAULT_CSV_OUT = HERE / "cambios_portadas.csv"
REFERENCE_VIEW = 3218
REBUILD_CAMPO = "ir_ui_view.{view_id}." + lib.REBUILD_SECTION + ".rebuild"
IMAGE_FLAGS = (("has_hero", "Hero", "microsite_hero_image"), ("has_intro", "SEC1", "microsite_intro_image"),
               ("has_banner", lib.STRIP_SECTION, "microsite_banner_image"))


def load_sites(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    for row in rows:
        for key in ("site", "company_id", "view_id"):
            row[key] = int(row[key])
    return rows


def load_archs(arch_dir: Path, view_id: int) -> dict[str, str]:
    path = arch_dir / f"arch_before_{view_id}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not all(isinstance(v, str) and v for v in data.values()):
        raise ValueError(f"{path}: expected a {{lang: arch}} object")
    return data


def company_flags(row: dict, omitted: list[str]) -> list[str]:
    """Flags that need the database columns of the manifest."""
    flags = []
    if row.get("has_about") == "0" and "Acerca" in omitted:
        flags.append("company microsite_about_text is EMPTY too: client must supply the texts")
    for key, section, image in IMAGE_FLAGS:
        if row.get(key) == "0" and section not in omitted:
            flags.append(f"company has NO {image}: the {section} background will be empty until a picture is uploaded")
    if row.get("hidden") == "1":
        flags.append("site hidden from the directory (normalized anyway)")
    return flags


def oracle_check(archs: dict[str, str]) -> str:
    """Compare the term port with Odoo's extractor on every language."""
    verified = 0
    for lang, arch in archs.items():
        oracle = terms.oracle_terms(arch)
        if oracle is None:
            return "odoo.tools.translate not importable: term port NOT cross-checked"
        if oracle != terms.extract_terms(arch):
            return f"TERM MISMATCH in {lang}: port and odoo.tools.translate disagree"
        verified += 1
    return f"terms cross-checked with odoo.tools.translate on {verified} languages"


def short_texts(archs: dict[str, str]) -> list[str]:
    lines = []
    for lang in sorted(archs):
        t = rb.extract_site_texts(archs[lang])
        cols = "; ".join(f"col{n}: {lib.truncate(c.title, 24)} / {lib.truncate(c.text, 36)}"
                         for n, c in sorted(t.columns.items())) or "-"
        lines.append(f"    {lang}: h1={lib.truncate(t.h1, 32)!r} sec1={lib.truncate(t.sec1, 44)!r} "
                     f"strip={lib.truncate(t.separador, 32)!r} acerca[{cols}]")
    return lines


def process_site(row: dict, reference: dict[str, str], arch_dir: Path) -> tuple[list[str], dict | None]:
    """Report lines and the CSV row (``None`` when the site fails)."""
    view_id, slug, company_id = row["view_id"], row["slug"], row["company_id"]
    before = load_archs(arch_dir, view_id)
    lines = [f"== {slug} (site {row['site']}, company {company_id}, view {view_id})"]
    try:
        after, omitted, flags = rb.rebuild_archs(reference, before, company_id, slug)
    except lib.ArchError as exc:
        lines.append(f"  ERROR: {exc}")
        return lines, None
    errors = check.validate_rebuilt(after, before, reference, company_id, slug, omitted)
    before_list, after_list = rb.section_list(before[lib.DEFAULT_PRIMARY_LANG]), rb.section_list(after[lib.DEFAULT_PRIMARY_LANG])
    lines.append(f"  sections: {before_list}  ->  {after_list}")
    flags += company_flags(row, omitted)
    lines += [f"  FLAG: {flag}" for flag in flags]
    lines.append("  " + oracle_check(after))
    lines += short_texts(after)
    if errors:
        lines += [f"  ERROR: {error}" for error in errors]
        return lines, None
    out = arch_dir / f"arch_after_{view_id}.json"
    out.write_text(json.dumps(after, ensure_ascii=False, indent=1), encoding="utf-8")
    lines.append(f"  written: {out}")
    motivo = "normalize homepage to the standard skeleton"
    if omitted:
        motivo += f"; omitted {', '.join(omitted)}"
    if flags:
        motivo += "; flags: " + " | ".join(flags)
    return lines, {"site": row["site"], "campo": REBUILD_CAMPO.format(view_id=view_id), "valor_anterior": before_list,
                   "valor_nuevo": out.name, "confianza": "1.00", "motivo": motivo}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sites", type=Path, default=DEFAULT_SITES, help="manifest of the sites to normalize")
    ap.add_argument("--arch-dir", type=Path, default=lib.DEFAULT_ARCH_ROOT,
                    help="directory of arch_before_<view>.json; arch_after_<view>.json files are written there")
    ap.add_argument("--reference", type=int, default=REFERENCE_VIEW, help="view id of the standard homepage")
    ap.add_argument("--csv-out", type=Path, default=DEFAULT_CSV_OUT, help="proposals CSV for aplicar.py")
    ap.add_argument("--report", type=Path, default=None,
                    help="report file (default: <arch-dir>/normalizacion_informe.txt)")
    args = ap.parse_args(argv)
    report_path = args.report or args.arch_dir / "normalizacion_informe.txt"
    reference = load_archs(args.arch_dir, args.reference)
    rows, report, failed = [], [f"Dry run: homepage normalization (reference view {args.reference})", ""], 0
    for site in load_sites(args.sites):
        lines, row = process_site(site, reference, args.arch_dir)
        report += lines + [""]
        if row is None:
            failed += 1
        else:
            rows.append(row)
    with open(args.csv_out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=lib.CSV_COLUMNS, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)
    report.append(f"{len(rows)} proposal row(s) written to {args.csv_out}; {failed} site(s) failed")
    text = "\n".join(report)
    report_path.write_text(text + "\n", encoding="utf-8")
    print(text)
    print(f"report: {report_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
