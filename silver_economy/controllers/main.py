# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, http
from odoo.exceptions import UserError
from odoo.http import request


class SilverEconomyController(http.Controller):
    def _get_active_silver_survey(self):
        """Return the active Silver Economy survey, if any."""
        return (
            request.env["survey.survey"]
            .sudo()
            .search(
                [("is_silver_economy", "=", True), ("active", "=", True)],
                limit=1,
            )
        )

    def _handle_silver_start(self, survey):
        """Common evaluation start flow: company check, cooldown, create."""
        user = request.env.user
        if not user.company_id:
            return request.render("silver_economy.silver_no_company", {})

        UserInput = request.env["survey.user_input"]
        next_date = UserInput._get_certification_cooldown_date(survey, user.company_id)
        if next_date and next_date > fields.Date.today():
            return request.render(
                "silver_economy.silver_cooldown",
                {"next_date": next_date, "survey": survey},
            )

        try:
            answer = UserInput._create_certification_answer(survey)
        except UserError as error:
            return request.render("silver_economy.silver_error", {"error": str(error)})

        return request.redirect(
            "/survey/start/%s?answer_token=%s"
            % (survey.access_token, answer.access_token)
        )

    @http.route("/silver_economy/start", type="http", auth="user", website=True)
    def silver_start_generic(self, **kwargs):
        """Generic entry point to start an evaluation (no token needed)."""
        survey = self._get_active_silver_survey()
        if not survey:
            return request.render(
                "silver_economy.silver_error",
                {
                    "error": _(
                        "There is no active Silver Economy questionnaire. "
                        "Please contact the administrator."
                    )
                },
            )
        return self._handle_silver_start(survey)

    @http.route(
        "/silver_economy/start/<string:survey_token>",
        type="http",
        auth="user",
        website=True,
    )
    def silver_start(self, survey_token, **kwargs):
        """Start a real Silver Economy evaluation from a survey token."""
        survey = (
            request.env["survey.survey"]
            .sudo()
            .search(
                [
                    ("access_token", "=", survey_token),
                    ("is_silver_economy", "=", True),
                    ("active", "=", True),
                ],
                limit=1,
            )
        )
        if not survey:
            return request.render(
                "silver_economy.silver_error",
                {"error": _("Questionnaire not found or inactive.")},
            )
        return self._handle_silver_start(survey)

    @http.route("/silver_economy/close", type="http", auth="user", website=True)
    def silver_close(self, **kwargs):
        """Redirect back to My Evaluations in the backend.

        Used by the 'Close' button on the survey completion page to avoid the
        Odoo 19 frontend rewriting the /web#action=... URL.
        """
        return request.redirect("/web#action=silver_economy.action_silver_evaluations")

    @http.route("/silver-economy", type="http", auth="public", website=True)
    def silver_economy_page(self, **kwargs):
        """Public information page about Silver Economy (Trainings)."""
        return request.render(
            "silver_economy.silver_economy_page",
            {"survey": self._get_active_silver_survey()},
        )

    @http.route(
        "/silver-economy/instructions", type="http", auth="public", website=True
    )
    def silver_instructions_page(self, **kwargs):
        """Public page with the Silver Economy exam instructions."""
        return request.render(
            "silver_economy.silver_instructions_page",
            {"survey": self._get_active_silver_survey()},
        )
