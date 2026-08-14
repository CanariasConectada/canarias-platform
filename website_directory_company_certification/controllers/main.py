# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields
from odoo.http import request

from odoo.addons.website_directory.controllers.main import WebsiteDirectory


class WebsiteDirectoryCertification(WebsiteDirectory):
    """Plug the certification filter into the directory extension hooks."""

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
        values["selected_certification"] = (kw.get("certification") or "").strip()
        values["certification_types"] = (
            request.env["certification.type"].sudo().search([])
        )
        return values
