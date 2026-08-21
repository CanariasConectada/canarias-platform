# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from werkzeug.urls import url_encode

from odoo import fields
from odoo.http import request

from odoo.addons.website_directory.controllers.main import WebsiteDirectory

PARAM = "certification"


class WebsiteDirectoryCertification(WebsiteDirectory):
    """Plug the certification filter into the directory extension hooks."""

    def _certification_url(self, url, kw, code):
        """The current address with the certification tick replaced by ``code``.

        Every other active filter (category, search, zone...) is carried over
        verbatim. Building this server side rather than appending
        ``?certification=...`` straight onto ``base_url`` in the template is
        what stops a click on "Sostenibilidad" from silently throwing away
        the category filter -- reported 2026-08-21 ("me borras el filtro de
        categoría"). Same pattern as
        ``website_directory_company_facilities._facility_url``.
        """
        args = {
            key: value
            for key, value in kw.items()
            if key not in (PARAM, "page") and value
        }
        if code:
            args[PARAM] = code
        query = url_encode(args)
        return "%s?%s" % (url, query) if query else url

    def _get_certification_filter_domain(self, code):
        """Entries of companies holding a valid seal of the given vertical."""
        return [
            (
                "company_id.certification_ids",
                "any",
                [
                    ("type_id.code", "=", code),
                    ("level", "!=", "none"),
                    ("expiry_date", ">=", fields.Date.today()),
                ],
            )
        ]

    def _get_extra_filter_domain(self, kw):
        domain = super()._get_extra_filter_domain(kw)
        code = (kw.get("certification") or "").strip()
        if code and request.env["certification.type"].sudo().search_count(
            [("code", "=", code)]
        ):
            domain += self._get_certification_filter_domain(code)
        return domain

    def _get_extra_pager_args(self, kw):
        args = super()._get_extra_pager_args(kw)
        if kw.get("certification"):
            args["certification"] = kw["certification"]
        return args

    def _prepare_directory_values(self, page=1, zone=None, url="/comercio", **kw):
        values = super()._prepare_directory_values(page=page, zone=zone, url=url, **kw)
        selected = (kw.get("certification") or "").strip()
        values["selected_certification"] = selected
        values["certification_types"] = (
            request.env["certification.type"].sudo().search([])
        )
        values["certification_urls"] = {
            cert_type.code: self._certification_url(
                url, kw, "" if selected == cert_type.code else cert_type.code
            )
            for cert_type in values["certification_types"]
        }
        return values
