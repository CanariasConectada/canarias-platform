# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import csv
import io
import json
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

VERSION = "19.0.2.20.0"
REVIEW_CSV_NAME = f"legacy-homepage-cover-review-{VERSION}.csv"


def _backup_name(view_id):
    return f"legacy-homepage-backup-{view_id}-{VERSION}.json"


def _backup_arch(env, view_id):
    """Keep the page as it is now, every language, attached to its view.

    Same shape as the 19.0.2.13.0 backup (the jsonb of the seven
    languages). Idempotent: only the superuser's first backup of this
    version counts, a later run keeps it.
    """
    Attachment = env["ir.attachment"].sudo()
    name = _backup_name(view_id)
    existing = Attachment.search_count(
        [
            ("res_model", "=", "ir.ui.view"),
            ("res_id", "=", view_id),
            ("name", "=", name),
            ("create_uid", "=", SUPERUSER_ID),
        ]
    )
    if existing:
        return False
    env.cr.execute("SELECT arch_db FROM ir_ui_view WHERE id = %s", [view_id])
    arch_db = env.cr.fetchone()[0]
    Attachment.create(
        {
            "name": name,
            "type": "binary",
            "mimetype": "application/json",
            "raw": json.dumps(arch_db, ensure_ascii=False, indent=1).encode(),
            "res_model": "ir.ui.view",
            "res_id": view_id,
        }
    )
    return True


def migrate(cr, version):
    """The cover and the picture strips of the imported homepages read from
    the company (``res.company._relink_cover_from_authoring_copy``).

    1. Every imported homepage (``_get_legacy_homepage_views``) is backed
       up, all languages, as ``legacy-homepage-backup-<view_id>-19.0.2.20.0.json``.
    2. Mode ``cover``: button and strip titles go live where the company
       has a value, the H1 where it already shows the resolved title, the
       backgrounds where the company image is the same file. Nothing else
       of the page is touched; one savepoint per page.
    3. What stayed as typed is listed in ``legacy-homepage-cover-review-19.0.2.20.0.csv``
       (administrators only); every visible text change is logged.

    Idempotent: a second run relinks nothing and keeps the first backups.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Company = env["res.company"]
    views = Company._get_legacy_homepage_views()
    backed_up = sum(1 for view in views if _backup_arch(env, view.id))
    _logger.info(
        "Legacy homepage covers: %d pages found, %d backed up.", len(views), backed_up
    )
    stats = Company._relink_legacy_homepage_live_data(views=views, mode="cover")
    for stat in stats:
        _logger.info(
            "Legacy homepage cover view %s (company %s): %s; relinked=%s "
            "kept_static=%s notes=%s",
            stat["view_id"],
            stat["company_id"],
            (
                f"skipped ({stat['skipped']})"
                if stat["skipped"]
                else ("written" if stat["written"] else "unchanged")
            ),
            ",".join(stat["relinked"]) or "-",
            ",".join(f"{k['kind']}({k['reason']})" for k in stat["kept_static"]) or "-",
            "; ".join(stat["notes"]) or "-",
        )
    _logger.info(
        "Legacy homepage covers: %d written, %d unchanged, %d skipped, %d failed "
        "(of %d).",
        sum(1 for s in stats if s["written"]),
        sum(1 for s in stats if not s["written"] and not s["skipped"]),
        sum(1 for s in stats if s["skipped"] and not s["failed"]),
        sum(1 for s in stats if s["failed"]),
        len(stats),
    )
    _write_review_csv(env, stats)


def _cell(value):
    """A text cell a spreadsheet never reads as a formula."""
    value = str(value or "")
    return f"'{value}" if value[:1] in ("=", "+", "-", "@") else value


def _write_review_csv(env, stats):
    """Every cover value a page still shows as typed, for the consultants.
    Rewritten on every run, so it always matches the pages."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "company_id",
            "company",
            "domain",
            "kind",
            "shown_on_page",
            "company_value",
            "reason",
        ]
    )
    Company = env["res.company"].sudo()
    for stat in stats:
        company = Company.browse(stat["company_id"])
        row = [company.id, _cell(company.name), company.website_id.domain or ""]
        if stat["failed"] or stat["skipped"]:
            writer.writerow(row + ["page", "", "", stat["skipped"] or "failed"])
        for kept in stat["kept_static"]:
            writer.writerow(
                row
                + [
                    kept["kind"],
                    _cell(kept["shown"]),
                    _cell(kept["live"]),
                    kept["reason"],
                ]
            )
    values = {
        "name": REVIEW_CSV_NAME,
        "type": "binary",
        "mimetype": "text/csv",
        "raw": buffer.getvalue().encode(),
        "res_model": False,
        "res_id": 0,
        "public": False,
    }
    Attachment = env["ir.attachment"].sudo()
    existing = Attachment.search(
        [
            ("name", "=", REVIEW_CSV_NAME),
            ("res_model", "=", False),
            ("create_uid", "=", SUPERUSER_ID),
        ],
        order="id asc",
        limit=1,
    )
    if existing:
        existing.write(values)
    else:
        Attachment.create(values)
