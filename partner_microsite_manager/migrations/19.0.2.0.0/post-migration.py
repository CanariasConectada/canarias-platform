# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

MODULE = "partner_microsite_manager"
SOURCE_LANG = "es_ES"
BASE_LANG = "en_US"

# The views whose Spanish must own its own jsonb key (see 19.0.1.7.0: en_US is
# the technical base of a translatable column, and anything loaded later that
# writes English into the base would silently replace the Spanish source).
LEGAL_VIEW_REFS = [
    "microsite_privacy_policy_content",
    "microsite_cookies_policy_content",
    "microsite_terms_conditions_content",
    "microsite_legal_notice_content",
    "microsite_legal_language_note",
    "microsite_privacy_policy",
    "microsite_cookies_policy",
    "microsite_terms_conditions",
    "microsite_legal_notice",
]


def migrate(cr, version):
    """Legal pages cutover: one canonical text, on every site, in every footer.

    Runs after the XML of this version loaded the rewritten legal templates
    (the legacy canonical text plus the GDPR sections it lacked), and:

    1. stamps the freshly loaded Spanish arch into an ``es_ES`` key of its own
       for the legal views, so nothing that later writes the ``en_US`` base can
       cost them their Spanish (the 2026-08-14 lesson, see 19.0.1.7.0);
    2. retires the per-website copy-on-write legal pages inherited from the
       legacy that shadowed these global pages (custom merchant texts are kept
       and logged);
    3. enables the cookies bar on every website — the platform sets optional
       ``odoo_utm_*`` cookies and Odoo only gates them behind consent when the
       bar is on — and replaces the stock English ``/cookie-policy`` pages
       with a 301 to ``/politica-cookies``;
    4. queues machine translation of the legal templates into the other six
       languages (the pages carry a Spanish-prevails clause for exactly this
       reason).

    Every step is idempotent, so re-running the upgrade is safe.
    """
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    view_ids = []
    for ref in LEGAL_VIEW_REFS:
        view = env.ref(f"{MODULE}.{ref}", raise_if_not_found=False)
        if view:
            view_ids.append(view.id)
    if view_ids:
        cr.execute(
            """
            UPDATE ir_ui_view
               SET arch_db = jsonb_set(arch_db, %s, arch_db -> %s)
             WHERE id IN %s
               AND arch_db ? %s
            """,
            ([SOURCE_LANG], BASE_LANG, tuple(view_ids), BASE_LANG),
        )
        _logger.info(
            "%s: %s legal views now hold their Spanish under %s",
            MODULE,
            cr.rowcount,
            SOURCE_LANG,
        )

    page_model = env["website.page"]
    result = page_model._pmm_retire_shadow_legal_pages()
    for url, website_name in result["kept"]:
        _logger.info(
            "%s: custom legal page kept and NOT replaced: %s on %s",
            MODULE,
            url,
            website_name,
        )
    page_model._pmm_enforce_cookie_consent()
    page_model._pmm_enqueue_legal_translations()
