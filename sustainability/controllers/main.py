# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request


class SustainabilityController(http.Controller):
    def _get_active_sustainability_survey(self):
        """Return the active Sustainability survey, if any."""
        return (
            request.env["survey.survey"]
            .sudo()
            .search(
                [("is_sustainability", "=", True), ("active", "=", True)],
                limit=1,
            )
        )

    def _handle_sustainability_start(self, survey):
        """Common evaluation start flow: company check, cooldown, create."""
        user = request.env.user
        if not user.company_id:
            return request.render("sustainability.sust_no_company", {})

        UserInput = request.env["survey.user_input"]
        next_date = UserInput._get_certification_cooldown_date(survey, user.company_id)
        if next_date and next_date > fields.Date.today():
            return request.render(
                "sustainability.sust_cooldown",
                {"next_date": next_date, "survey": survey},
            )

        try:
            answer = UserInput._create_certification_answer(survey)
        except UserError as error:
            return request.render("sustainability.sust_error", {"error": str(error)})

        return request.redirect(
            "/survey/start/%s?answer_token=%s"
            % (survey.access_token, answer.access_token)
        )

    @http.route("/sostenibilidad/start", type="http", auth="user", website=True)
    def sustainability_start_generic(self, **kwargs):
        """Generic entry point to start an evaluation (no token needed)."""
        survey = self._get_active_sustainability_survey()
        if not survey:
            return request.render(
                "sustainability.sust_error",
                {
                    "error": _(
                        "There is no active Sustainability questionnaire. "
                        "Please contact the administrator."
                    )
                },
            )
        return self._handle_sustainability_start(survey)

    @http.route(
        "/sostenibilidad/start/<string:survey_token>",
        type="http",
        auth="user",
        website=True,
    )
    def sustainability_start(self, survey_token, **kwargs):
        """Start a real Sustainability evaluation from a survey token."""
        survey = (
            request.env["survey.survey"]
            .sudo()
            .search(
                [
                    ("access_token", "=", survey_token),
                    ("is_sustainability", "=", True),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )
        if not survey:
            return request.render(
                "sustainability.sust_error",
                {"error": _("Questionnaire not found or inactive.")},
            )
        return self._handle_sustainability_start(survey)

    @http.route("/sostenibilidad/close", type="http", auth="user", website=True)
    def sustainability_close(self, **kwargs):
        """Redirect back to My Evaluations in the backend.

        Used by the 'Close' button on the survey completion page to avoid the
        Odoo 19 frontend rewriting the /web#action=... URL.
        """
        return request.redirect("/web#action=sustainability.action_sust_evaluations")

    @http.route("/sostenibilidad", type="http", auth="public", website=True)
    def sustainability_page(self, **kwargs):
        """Public information page about Sustainability (Trainings)."""
        return request.render(
            "sustainability.sust_economy_page",
            {"survey": self._get_active_sustainability_survey()},
        )

    @http.route(
        "/sostenibilidad/instrucciones", type="http", auth="public", website=True
    )
    def sustainability_instructions_page(self, **kwargs):
        """Public page with the Sustainability exam instructions."""
        return request.render(
            "sustainability.sust_instructions_page",
            {"survey": self._get_active_sustainability_survey()},
        )
