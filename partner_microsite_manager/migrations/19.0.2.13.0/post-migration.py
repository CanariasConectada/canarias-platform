# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import json
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

VERSION = "19.0.2.13.0"


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
    if Attachment.search_count(
        [
            ("res_model", "=", "ir.ui.view"),
            ("res_id", "=", view_id),
            ("name", "=", name),
        ],
        limit=1,
    ):
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
       templates (``_relink_legacy_homepage_live_data``), one savepoint per
       page; one log line per page says what was done.

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
    stats = Company._relink_legacy_homepage_live_data(views=views)
    for stat in stats:
        _logger.info(
            "Legacy homepage view %s (company %s): %s; relinked=%s inserted=%s "
            "dropped=%s restored=%s notes=%s",
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
            "; ".join(stat["notes"]) or "-",
        )
    _logger.info(
        "Legacy homepages: %d written, %d unchanged, %d skipped (of %d).",
        sum(1 for s in stats if s["written"]),
        sum(1 for s in stats if not s["written"] and not s["skipped"]),
        sum(1 for s in stats if s["skipped"]),
        len(stats),
    )
