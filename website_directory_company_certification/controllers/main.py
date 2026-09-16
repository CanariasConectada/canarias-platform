# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from werkzeug.urls import url_encode

from odoo import fields
from odoo.http import request

from odoo.addons.website_directory.controllers.main import WebsiteDirectory

PARAM = "certification"
SEPARATOR = ","


class WebsiteDirectoryCertification(WebsiteDirectory):
    """Plug the certification filter into the directory extension hooks.

    Several seals can be ticked at once and they NARROW: a visitor asking
    for Silver Economy and Sostenibilidad wants the shops holding both.
    Until 2026-09-15 the filter was one seal or the other ("es uno u
    otro"); the client asked for the "o" to become a "y", the same way the
    facilities filter already reads ("Wifi gratis" AND "Parking"). The
    parameter is a comma list, exactly like ``facility``.
    """

    def _selected_certification_codes(self, kw):
        """The codes in the query string, as codes that actually exist.

        Junk is dropped silently: a mistyped address should show the
        directory, not a traceback. The visitor's order is kept so the chips
        do not jump around.
        """
        raw = kw.get(PARAM) or ""
        candidates = []
        for chunk in raw.split(SEPARATOR):
            chunk = chunk.strip()
            if chunk and chunk not in candidates:
                candidates.append(chunk)
        if not candidates:
            return []
        existing = set(
            request.env["certification.type"]
            .sudo()
            .search([("code", "in", candidates)])
            .mapped("code")
        )
        return [code for code in candidates if code in existing]

    def _certification_url(self, url, kw, codes):
        """The current address with the ticked seals replaced by ``codes``.

        Every other active filter (category, search, zone...) is carried over
        verbatim. Building this server side rather than appending
        ``?certification=...`` straight onto ``base_url`` in the template is
        what stops a click on "Sostenibilidad" from silently throwing away
        the category filter -- reported 2026-08-21 ("me borras el filtro de
        categoría"). Same pattern as
        ``website_directory_company_facilities._facility_url``.
        """
        if isinstance(codes, str):
            codes = [codes] if codes else []
        args = {
            key: value
            for key, value in kw.items()
            if key not in (PARAM, "page") and value
        }
        if codes:
            args[PARAM] = SEPARATOR.join(codes)
        query = url_encode(args)
        return "%s?%s" % (url, query) if query else url

    def _get_certification_filter_domain(self, codes):
        """Entries of companies holding a valid seal of EVERY given vertical.

        One leaf per seal, so two ticks narrow rather than widen.
        """
        if isinstance(codes, str):
            codes = [codes]
        domain = []
        for code in codes:
            domain.append(
                (
                    "company_id.certification_ids",
                    "any",
                    [
                        ("type_id.code", "=", code),
                        ("level", "!=", "none"),
                        ("expiry_date", ">=", fields.Date.today()),
                    ],
                )
            )
        return domain

    def _get_extra_filter_domain(self, kw):
        domain = super()._get_extra_filter_domain(kw)
        codes = self._selected_certification_codes(kw)
        if codes:
            domain += self._get_certification_filter_domain(codes)
        return domain

    def _get_extra_pager_args(self, kw):
        args = super()._get_extra_pager_args(kw)
        codes = self._selected_certification_codes(kw)
        if codes:
            args[PARAM] = SEPARATOR.join(codes)
        return args

    def _prepare_directory_values(self, page=1, zone=None, url="/comercio", **kw):
        values = super()._prepare_directory_values(page=page, zone=zone, url=url, **kw)
        selected = self._selected_certification_codes(kw)
        values["selected_certifications"] = selected
        # Kept for templates and bridges written against the single value:
        # the first tick, or nothing.
        values["selected_certification"] = selected[0] if selected else ""
        values["certification_types"] = (
            request.env["certification.type"].sudo().search([])
        )
        # Each seal's address toggles that seal in or out of the current
        # set, leaving the others ticked.
        values["certification_urls"] = {
            cert_type.code: self._certification_url(
                url,
                kw,
                [code for code in selected if code != cert_type.code]
                if cert_type.code in selected
                else selected + [cert_type.code],
            )
            for cert_type in values["certification_types"]
        }
        return values
