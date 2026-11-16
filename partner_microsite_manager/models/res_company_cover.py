# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The cover and the picture strips of the legacy homepages, read from the
company (``tools/legacy_cover``). Split out of ``res_company.py`` (1.7k
lines); the engine that writes the pages stays there
(``_relink_legacy_homepage_live_data``)."""

from odoo import api, models

from ..tools import legacy_cover
from ..tools.homepage_completeness import classify_url

# Text kind -> the company field its live template renders.
COVER_TEXT_FIELDS = {
    "title": "microsite_title",
    "button": "microsite_button_text",
    "intro_title": "microsite_intro_title",
    "strip_title": "microsite_banner_title",
}
# Company field a person edits -> the cover kind that edit makes live. The
# title follows ``microsite_name`` (what the merchant types); the resolved
# ``microsite_title`` is what the page prints.
COVER_FIELD_KINDS = {
    "microsite_name": "title",
    "microsite_button_text": "button",
    "microsite_intro_title": "intro_title",
    "microsite_banner_title": "strip_title",
    **{field: kind for kind, (_slot, field) in legacy_cover.IMAGE_KINDS.items()},
}


class ResCompany(models.Model):
    _inherit = "res.company"

    def _microsite_cover_value(self, kind):
        self.ensure_one()
        return (self[COVER_TEXT_FIELDS[kind]] or "").strip()

    def _microsite_cover_image_checksum(self, field):
        """Checksum of the company's ``field`` picture, ``""`` without one."""
        self.ensure_one()
        attachment = (
            self.env["ir.attachment"]
            .sudo()
            .search(
                [
                    ("res_model", "=", "res.company"),
                    ("res_id", "=", self.id),
                    ("res_field", "=", field),
                ],
                limit=1,
            )
        )
        return attachment.checksum or ""

    def _microsite_cover_backgrounds(self, arch, kinds, report=None):
        """``{image kind: company URL}`` for the ``kinds`` whose background
        in ``arch`` is an attachment the company image may replace.

        With ``report`` (the migration) the picture must be the company's
        own, checksum for checksum: the page keeps showing what it showed,
        now read from the field. Without it (a human uploaded the image)
        the company image wins. Only an ``ir.attachment`` background is
        replaced; the stock pictures, external links and the company-field
        URL itself are left as they are. Never when the field is empty.
        """
        self.ensure_one()
        backgrounds = {}
        shown = legacy_cover.read_cover(arch)["backgrounds"]
        for kind in kinds:
            if kind not in legacy_cover.IMAGE_KINDS:
                continue
            _slot, field = legacy_cover.IMAGE_KINDS[kind]
            url_kind, ref = classify_url(shown.get(kind))
            if url_kind != "attachment":
                continue
            checksum = self._microsite_cover_image_checksum(field)
            reason = None
            if not checksum:
                reason = "live_empty"
            elif report is not None:
                old = self.env["ir.attachment"].sudo().browse(ref).exists()
                if old.checksum != checksum:
                    reason = "image_differs"
            if reason:
                if report is not None:
                    report["kept_static"].append(
                        {
                            "kind": kind,
                            "shown": shown.get(kind) or "",
                            "live": field,
                            "reason": reason,
                        }
                    )
                continue
            backgrounds[kind] = legacy_cover.company_image_url(self.id, field)
        return backgrounds

    @api.model
    def _relink_cover_from_authoring_copy(self, view, company):
        """The 19.0.2.20.0 migration's transform of ``view``: the cover only.

        Decided on the copy in the website's language (as the contact
        values, ``_relink_from_authoring_copy``) and applied to the base
        arch:

        - a text the page already shows (same value, ignoring case and
          whitespace) is left as typed, with its seven translations: the
          live template prints the single Spanish field in every language,
          so relinking it would only replace the translations. A later
          edit of that field relinks it (``res.company.write``);
        - the button and the two strip titles go live where the company
          value differs from the page; an empty field keeps the page's text
          (``live_empty``);
        - a cover title that differs is kept and listed (``differs``):
          forcing those is the owner's decision;
        - a background picture goes live when the company image is the same
          file (checksum); it carries no translation.
        """
        raw = self._get_arch_db_raw(view)
        base = raw.get("en_US") or view.arch_db or ""
        lang = view.website_id.default_lang_id.code
        authoring = next(
            (raw[code] for code in (lang, "es_ES", "en_US") if code and raw.get(code)),
            base,
        )
        shown = legacy_cover.read_cover(authoring)
        report = legacy_cover.empty_report()
        relink = []
        for kind, text in shown["texts"].items():
            value = company._microsite_cover_value(kind)
            if kind in shown["live"]:
                continue
            reason = None
            if text is None:
                reason = "markup"
            elif not value:
                reason = "live_empty"
            elif legacy_cover.same_value(text, value):
                # Already what the company says: keep the translations.
                continue
            elif kind == "title":
                reason = "differs"
            if reason:
                report["kept_static"].append(
                    {"kind": kind, "shown": text or "", "live": value, "reason": reason}
                )
                continue
            relink.append(kind)
            report["notes"].append(f"{kind}: {text!r} -> {value!r}")
        backgrounds = company._microsite_cover_backgrounds(
            base, legacy_cover.IMAGE_KINDS, report
        )
        new_arch, done = legacy_cover.relink_cover(base, relink, backgrounds)
        done["kept_static"] = report["kept_static"]
        done["notes"] = list(dict.fromkeys(report["notes"] + done["notes"]))
        return new_arch, done

    def _relink_cover_after(self, arch, new_arch, report, force):
        """The cover step of a builder save (``force`` empty) or of a human
        edit of ``force``: run on the contact step's result (``new_arch``,
        or ``arch`` when it changed nothing) and merged into its report."""
        self.ensure_one()
        source = new_arch or arch
        relink = [
            kind
            for kind in legacy_cover.TEXT_KINDS
            if kind in force and self._microsite_cover_value(kind)
        ]
        backgrounds = self._microsite_cover_backgrounds(source, force)
        cover_arch, cover = legacy_cover.relink_cover(source, relink, backgrounds)
        if not cover_arch:
            return new_arch, report
        merged = dict(report, skipped=None)
        for key in ("relinked", "restored", "notes", "present"):
            merged[key] = list(dict.fromkeys(report[key] + cover[key]))
        return cover_arch, merged
