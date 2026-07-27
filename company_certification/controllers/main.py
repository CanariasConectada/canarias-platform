# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request


class CompanyCertificationController(http.Controller):
    """Website entry points to start a certification evaluation.

    The heavy lifting (cooldown, answer creation) lives in
    ``survey.user_input._start_certification_evaluation``; this controller
    only translates the outcome into friendly website pages.
    """

    def _get_certification_type(self, code):
        return (
            request.env["certification.type"]
            .sudo()
            .search([("code", "=", code)], limit=1)
        )

    @http.route(
        "/certification/<string:code>",
        type="http",
        auth="public",
        website=True,
        sitemap=True,
    )
    def certification_landing(self, code, **kwargs):
        """Public page of one vertical: what it is, and its training material.

        Read as sudo on purpose — visitors have no access to
        ``certification.type``, and only the handful of presentation fields
        below ever reach the template. An unpublished or unknown vertical is
        a plain 404: answering 200 with an empty page would get it indexed.
        """
        cert_type = self._get_certification_type(code)
        if not cert_type or not cert_type.landing_published:
            return request.not_found()
        return request.render(
            "company_certification.certification_landing",
            {
                "cert_type": cert_type,
                "materials": cert_type.material_ids.filtered("attachment_id"),
            },
        )

    @http.route(
        "/certification/<string:code>/start",
        type="http",
        auth="user",
        website=True,
    )
    def certification_start(self, code, **kwargs):
        """Start (or refuse with an explanation) a real evaluation."""
        cert_type = self._get_certification_type(code)
        if not cert_type:
            return request.render(
                "company_certification.certification_error",
                {"error": _("Unknown certification type.")},
            )
        user = request.env.user
        if not user.company_id:
            return request.render(
                "company_certification.certification_no_company",
                {"cert_type": cert_type},
            )
        last = request.env["survey.user_input"]._get_last_done_attempt(
            cert_type, user.company_id
        )
        if (
            last
            and last.next_attempt_date
            and last.next_attempt_date > fields.Date.today()
        ):
            return request.render(
                "company_certification.certification_cooldown",
                {"next_date": last.next_attempt_date, "cert_type": cert_type},
            )
        try:
            url = request.env["survey.user_input"]._start_certification_evaluation(
                cert_type
            )
        except UserError as error:
            return request.render(
                "company_certification.certification_error", {"error": str(error)}
            )
        return request.redirect(url)

    @http.route("/certification/<string:code>/close", type="http", auth="user")
    def certification_close(self, code, **kwargs):
        """Send the user back to the vertical's backend evaluation list."""
        cert_type = self._get_certification_type(code)
        if cert_type and cert_type.action_id:
            return request.redirect("/odoo/action-%d" % cert_type.action_id.id)
        return request.redirect("/odoo")
