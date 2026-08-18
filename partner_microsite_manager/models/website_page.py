# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

import hashlib
import logging
import re

from odoo import api, models

_logger = logging.getLogger(__name__)

# The URLs of the legal pages this module serves globally (no website_id).
LEGAL_URLS = [
    "/politica-privacidad",
    "/politica-cookies",
    "/terminos-condiciones",
    "/aviso-legal",
]

# The legacy site generator seeded placeholder legal pages on late-created
# shops: "Contenido de política de cookies para <shop>." and nothing else.
# They carry no legal text at all, so they are as safe to retire as the
# canonical copies.
STUB_RE = re.compile(r"Contenido de .{0,120} para", re.IGNORECASE)
STUB_MAX_LEN = 2500


class WebsitePage(models.Model):
    _inherit = "website.page"

    @api.model
    def _pmm_retire_shadow_legal_pages(self, min_majority=6):
        """Retire the per-site legal pages that shadow the global ones.

        The migration from the legacy platform imported one copy-on-write
        legal page per website (identical canonical text on ~166 sites, plus
        empty placeholder stubs), and a website-specific page always wins over
        a global one, so the maintained templates of this module never served
        those sites. This deletes:

        * the *majority* copies — the groups sharing one identical text across
          at least ``min_majority`` websites and more than half of the per-site
          pages of that URL (the canonical legacy text), and
        * the placeholder stubs ("Contenido de ... para <shop>").

        Anything else is a text a merchant genuinely wrote (aeropatín has its
        own long policies) and is deliberately KEPT — replacing a merchant's
        own legal text with ours is not this module's call. Kept pages are
        logged so the report of every upgrade names them.

        Idempotent: on a second run the groups are empty and nothing matches.
        Returns ``{"deleted": n, "kept": [(url, website_name), ...]}``.
        """
        deleted = 0
        kept = []
        for url in LEGAL_URLS:
            pages = self.sudo().search([("url", "=", url), ("website_id", "!=", False)])
            if not pages:
                continue
            groups = {}
            for page in pages:
                arch = page.view_id.with_context(lang=None).arch_db or ""
                # Group by the visible TEXT, not the markup: the legacy import
                # left the same canonical text with tiny markup differences on
                # a handful of sites (the portal and the zones), and what
                # makes a page safe to retire is its wording being the
                # canonical one.
                normalized = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", arch))
                digest = hashlib.md5(normalized.encode()).hexdigest()
                groups.setdefault(digest, self.browse())
                groups[digest] |= page
            majority = max(groups.values(), key=len)
            to_delete = self.browse()
            if len(majority) >= min_majority and len(majority) * 2 > len(pages):
                to_delete |= majority
            for group in groups.values():
                if group == majority and group <= to_delete:
                    continue
                sample = re.sub(
                    r"<[^>]+>",
                    " ",
                    group[0].view_id.with_context(lang=None).arch_db or "",
                )
                if len(sample) <= STUB_MAX_LEN and STUB_RE.search(sample):
                    to_delete |= group
            for page in pages - to_delete:
                kept.append((url, page.website_id.name))
                _logger.info(
                    "Legal page kept (custom text): %s on %s",
                    url,
                    page.website_id.name,
                )
            deleted += len(to_delete)
            to_delete.unlink()
        _logger.info(
            "Retired %s shadow legal pages; %s custom pages kept", deleted, len(kept)
        )
        return {"deleted": deleted, "kept": kept}

    @api.model
    def _pmm_enforce_cookie_consent(self):
        """One consent story on every website.

        The platform sets first-party campaign attribution cookies
        (``odoo_utm_*``, flagged ``optional`` by Odoo) and Odoo only withholds
        optional cookies until consent *when the cookies bar is enabled* —
        with the bar off they are set without asking. Since mass mailing links
        carry utm parameters, every website needs the bar.

        Enabling the bar makes core auto-create a per-site ``/cookie-policy``
        page holding Odoo's stock English text, which contradicts the actual
        cookie policy. Those pages (the 133 inherited ones and the ones the
        toggle just created) are deleted and the URL is 301-redirected to
        ``/politica-cookies`` instead, so the link inside every cookies bar
        popup keeps working.

        Idempotent: the writes filter on state and the rewrite is looked up
        before being created.
        """
        websites = self.env["website"].sudo().search([("cookies_bar", "=", False)])
        # Core's write() resolves ``self.id`` in its cookies_bar handling, so
        # one write per record, not one write on the recordset.
        for website in websites:
            website.write({"cookies_bar": True})
        _logger.info("Cookies bar enabled on %s websites", len(websites))

        stock_pages = self.sudo().search(
            [("url", "=", "/cookie-policy"), ("website_id", "!=", False)]
        )
        count = len(stock_pages)
        stock_pages.unlink()
        _logger.info("Deleted %s stock /cookie-policy pages", count)

        rewrite_model = self.env["website.rewrite"].sudo()
        rewrite = rewrite_model.search(
            [("url_from", "=", "/cookie-policy"), ("website_id", "=", False)],
            limit=1,
        )
        if not rewrite:
            rewrite_model.create(
                {
                    "name": "Cookie policy → Política de Cookies",
                    "url_from": "/cookie-policy",
                    "url_to": "/politica-cookies",
                    "redirect_type": "301",
                }
            )
            _logger.info("Created 301 rewrite /cookie-policy -> /politica-cookies")
        return len(websites)

    @api.model
    def _pmm_enqueue_legal_translations(self):
        """Queue machine translation of the four global legal templates.

        ``website_auto_translate`` deliberately skips views without a
        ``website_id`` on ordinary writes (an addon's view is normally worded
        in its .po files), so the legal pages are enqueued explicitly here.
        The queued translations are the reason every legal page carries the
        prevailing-language clause: the non-Spanish versions are machine
        translations and say so.

        Safe when the translator module is absent (returns 0) and idempotent
        (``_enqueue_many`` reuses or reopens existing jobs).
        """
        if "auto.translate.job" not in self.env:
            return 0
        refs = [
            "partner_microsite_manager.microsite_privacy_policy_content",
            "partner_microsite_manager.microsite_cookies_policy_content",
            "partner_microsite_manager.microsite_terms_conditions_content",
            "partner_microsite_manager.microsite_legal_notice_content",
            "partner_microsite_manager.microsite_legal_language_note",
        ]
        views = self.env["ir.ui.view"].sudo()
        for ref in refs:
            view = self.env.ref(ref, raise_if_not_found=False)
            if view:
                views |= view
        if not views:
            return 0
        langs = self.env["auto.translate.mixin"]._auto_translate_target_langs()
        jobs = (
            self.env["auto.translate.job"]
            .sudo()
            ._enqueue_many(views, ["arch_db"], langs)
        )
        _logger.info("Enqueued %s translation jobs for the legal templates", len(jobs))
        return len(jobs)
