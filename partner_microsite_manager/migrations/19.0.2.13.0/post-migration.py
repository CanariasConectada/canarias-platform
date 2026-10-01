# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import csv
import io
import json
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

VERSION = "19.0.2.13.0"
REVIEW_CSV_NAME = f"legacy-homepage-review-{VERSION}.csv"


def _backup_name(view_id):
    return f"legacy-homepage-backup-{view_id}-{VERSION}.json"


def _backup_arch(env, view_id):
    """Keep the page as it was, every language, attached to its view.

    Read straight from the column: the jsonb holds the seven languages, and
    restoring is writing that dict back. Idempotent: a page backed up by an
    earlier run keeps its first (original) backup.
    """
    Attachment = env["ir.attachment"].sudo()
    name = _backup_name(view_id)
    # Only the migration's own (superuser) backup counts, never a
    # same-name attachment somebody else created.
    if env["res.company"]._find_legacy_homepage_backup(view_id):
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
    """Every value of the imported homepages read from the company.

    1. The imported homepages are resolved in SQL (``_get_legacy_homepage_views``:
       the "/" page with an importer key, zone companies excluded).
    2. Each page's arch, all languages, is saved as a JSON attachment of
       its view (``legacy-homepage-backup-<view_id>-19.0.2.13.0.json``).
    3. The values typed in by the importer become t-calls of the live
       templates (``_relink_legacy_homepage_live_data``, mode
       ``migration``), one savepoint per page; one log line per page says
       what was done. An email, address, web or map the page shows
       differently from the company is kept as it is (the page keeps what
       it shows until a person edits that value).
    4. Those kept values are listed in ``legacy-homepage-review-19.0.2.13.0.csv``
       (no record, administrators only) for the consultants to reconcile.

    Idempotent: a second run finds nothing to relink and keeps the first
    backups.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    Company = env["res.company"]
    views = Company._get_legacy_homepage_views()
    backed_up = sum(1 for view in views if _backup_arch(env, view.id))
    _logger.info(
        "Legacy homepages: %d pages found, %d backed up as attachments.",
        len(views),
        backed_up,
    )
    stats = Company._relink_legacy_homepage_live_data(views=views, mode="migration")
    for stat in stats:
        _logger.info(
            "Legacy homepage view %s (company %s): %s; relinked=%s inserted=%s "
            "dropped=%s restored=%s kept_static=%s notes=%s",
            stat["view_id"],
            stat["company_id"],
            (
                f"skipped ({stat['skipped']})"
                if stat["skipped"]
                else ("written" if stat["written"] else "unchanged")
            ),
            ",".join(stat["relinked"]) or "-",
            ",".join(stat["inserted"]) or "-",
            ",".join(stat["dropped"]) or "-",
            ",".join(stat["restored"]) or "-",
            ",".join(f"{k['kind']}({k['reason']})" for k in stat["kept_static"]) or "-",
            "; ".join(stat["notes"]) or "-",
        )
    kept = [k for stat in stats for k in stat["kept_static"]]
    _logger.info(
        "Legacy homepages: %d written, %d unchanged, %d skipped, %d failed "
        "(of %d); %d values kept static (%s).",
        sum(1 for s in stats if s["written"]),
        sum(1 for s in stats if not s["written"] and not s["skipped"]),
        sum(1 for s in stats if s["skipped"] and not s["failed"]),
        sum(1 for s in stats if s["failed"]),
        len(stats),
        len(kept),
        ", ".join(
            f"{kind}={sum(1 for k in kept if k['kind'] == kind)}"
            for kind in sorted({k["kind"] for k in kept})
        )
        or "-",
    )
    _write_review_csv(env, stats)


def _write_review_csv(env, stats):
    """One CSV for the consultants: every value a page still shows as typed
    by the importer because it differs from the company (or the company has
    none). Rewritten on every run, so it always matches the pages."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "company_id",
            "company",
            "domain",
            "kind",
            "shown_on_page",
            "contact_value",
            "reason",
        ]
    )
    Company = env["res.company"].sudo()
    for stat in stats:
        company = Company.browse(stat["company_id"])
        if stat["failed"] or stat["skipped"] == "translation structure mismatch":
            # The whole page kept its importer values: not only in the log.
            writer.writerow(
                [
                    company.id,
                    company.name,
                    company.website_id.domain or "",
                    "page",
                    "",
                    "",
                    "failed" if stat["failed"] else "skipped_translation_mismatch",
                ]
            )
        for kept in stat["kept_static"]:
            writer.writerow(
                [
                    company.id,
                    company.name,
                    company.website_id.domain or "",
                    kept["kind"],
                    kept["shown"],
                    kept["live"],
                    kept["reason"],
                ]
            )
    # Not attached to any record: an attachment without res_model is only
    # readable by administrators (and its creator, the superuser).
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
