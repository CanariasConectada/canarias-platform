# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    # NOTE for maintainers: silver_economy and sustainability both extend
    # survey.user_input with the same shared fields and method names. Shared
    # methods (computes, override actions, helpers) keep an IDENTICAL body in
    # both modules and read the module-specific parameters through the
    # cooperative hook ``survey.survey._get_certification_config()``, so the
    # behaviour is correct no matter which module wins in the registry MRO.

    company_id = fields.Many2one(
        "res.company",
        string="Evaluated Company",
        index=True,
        help="Company this evaluation belongs to",
    )

    certification_level = fields.Selection(
        [
            ("none", "No badge"),
            ("bronze", "Bronze"),
            ("silver", "Silver"),
            ("gold", "Gold"),
        ],
        string="Certification Level",
        compute="_compute_certification_level",
        store=True,
    )

    next_attempt_date = fields.Date(
        string="Next Attempt Available",
        compute="_compute_next_attempt_date",
        store=True,
    )
    expiry_date = fields.Date(
        string="Badge Expiry Date",
        compute="_compute_expiry_date",
        store=True,
    )

    # Manual override audit trail
    is_manually_overridden = fields.Boolean(
        string="Score Manually Edited",
        default=False,
        help="Set when a certification manager overrode the computed score",
    )
    override_scoring_total = fields.Float(
        string="Overridden Score",
        readonly=True,
        digits=(10, 2),
        help="Score imposed by the manager; reapplied whenever the survey "
        "scoring is recomputed",
    )
    override_user_id = fields.Many2one(
        "res.users",
        string="Edited By",
        readonly=True,
    )
    override_date = fields.Datetime(
        string="Edit Date",
        readonly=True,
    )
    override_reason = fields.Text(
        string="Edit Reason",
    )
    original_scoring_total = fields.Float(
        string="Original Score",
        readonly=True,
        digits=(10, 2),
    )

    # ------------------------------------------------------------------
    # Computes (shared bodies)
    # ------------------------------------------------------------------

    def _compute_scoring_values(self):
        """Reapply manual overrides after the standard recomputation.

        Without this, any recomputation of ``scoring_total`` (triggered by
        answer lines or a direct call) silently discards the score imposed by
        a manager.
        """
        super()._compute_scoring_values()
        for user_input in self.filtered("is_manually_overridden"):
            user_input.scoring_total = user_input.override_scoring_total
            config = user_input.survey_id._get_certification_config()
            if config and config["max_score"] > 0:
                user_input.scoring_percentage = round(
                    user_input.override_scoring_total * 100 / config["max_score"], 2
                )

    @api.depends("scoring_total", "survey_id")
    def _compute_certification_level(self):
        # Deliberately not dependent on the survey thresholds: changing the
        # thresholds must not retroactively rewrite already-awarded badges.
        for user_input in self:
            survey = user_input.survey_id
            config = survey._get_certification_config() if survey else None
            if not config or survey.scoring_type == "no_scoring":
                user_input.certification_level = "none"
                continue
            score = user_input.scoring_total
            if config["max_score"] <= 0 or score < config["bronze_min"]:
                user_input.certification_level = "none"
            elif score < config["silver_min"]:
                user_input.certification_level = "bronze"
            elif score < config["gold_min"]:
                user_input.certification_level = "silver"
            else:
                user_input.certification_level = "gold"

    @api.depends("create_date", "certification_level", "state", "survey_id")
    def _compute_next_attempt_date(self):
        for user_input in self:
            config = user_input.survey_id._get_certification_config()
            if user_input.state != "done" or not config or not user_input.create_date:
                user_input.next_attempt_date = False
                continue
            start = user_input.create_date.date()
            if user_input.certification_level == "none":
                delta = relativedelta(months=config["cooldown_months"])
            else:
                delta = relativedelta(years=config["validity_years"])
            user_input.next_attempt_date = start + delta

    @api.depends("create_date", "certification_level", "state", "survey_id")
    def _compute_expiry_date(self):
        for user_input in self:
            config = user_input.survey_id._get_certification_config()
            if (
                user_input.state != "done"
                or user_input.certification_level == "none"
                or not config
                or not user_input.create_date
            ):
                user_input.expiry_date = False
            else:
                user_input.expiry_date = user_input.create_date.date() + relativedelta(
                    years=config["validity_years"]
                )

    # ------------------------------------------------------------------
    # Evaluation lifecycle (shared bodies)
    # ------------------------------------------------------------------

    @api.model
    def _get_certification_cooldown_date(self, survey, company):
        """Return the date until which the company must wait, or ``False``."""
        last_attempt = self.sudo().search(
            [
                ("survey_id", "=", survey.id),
                ("company_id", "=", company.id),
                ("state", "=", "done"),
                ("test_entry", "=", False),
            ],
            order="create_date desc",
            limit=1,
        )
        if (
            last_attempt
            and last_attempt.next_attempt_date
            and last_attempt.next_attempt_date > fields.Date.today()
        ):
            return last_attempt.next_attempt_date
        return False

    @api.model
    def _create_certification_answer(self, survey):
        """Create a real (non test) answer for the current user's company.

        Validates that the user has a company and that the company-wide
        cooldown has elapsed. Raises :class:`UserError` otherwise.
        """
        user = self.env.user
        if not user.company_id:
            raise UserError(
                _("You must have a company assigned to take the evaluation.")
            )
        next_date = self._get_certification_cooldown_date(survey, user.company_id)
        if next_date:
            raise UserError(_("You cannot take a new evaluation until %s.", next_date))
        return self.sudo().create(
            {
                "survey_id": survey.id,
                "partner_id": user.partner_id.id,
                "company_id": user.company_id.id,
                "test_entry": False,
            }
        )

    def _mark_done(self):
        res = super()._mark_done()
        for user_input in self:
            if (
                user_input.survey_id.is_sustainability
                and user_input.company_id
                and not user_input.test_entry
                and user_input.certification_level != "none"
            ):
                user_input._send_sustainability_badge_notification()
        return res

    # ------------------------------------------------------------------
    # Manual override (shared bodies)
    # ------------------------------------------------------------------

    def action_override_score(self, new_score, reason=False):
        """Override the computed score, keeping an audit trail."""
        self.ensure_one()
        config = self.survey_id._get_certification_config()
        if not config:
            raise UserError(_("This answer does not belong to a certification survey."))
        if not self.env.user.has_group(config["manager_group"]):
            raise UserError(_("Only certification managers can edit scores."))
        vals = {
            "override_scoring_total": new_score,
            "is_manually_overridden": True,
            "override_user_id": self.env.user.id,
            "override_date": fields.Datetime.now(),
            "override_reason": reason,
        }
        if not self.is_manually_overridden:
            vals["original_scoring_total"] = self.scoring_total
        self.write(vals)
        self._compute_scoring_values()

    def action_reset_override(self):
        """Discard the manual override and restore the computed score."""
        self.ensure_one()
        config = self.survey_id._get_certification_config()
        if not config:
            raise UserError(_("This answer does not belong to a certification survey."))
        if not self.env.user.has_group(config["manager_group"]):
            raise UserError(_("Only certification managers can revert score edits."))
        if not self.is_manually_overridden:
            return
        self.write(
            {
                "is_manually_overridden": False,
                "override_scoring_total": 0.0,
                "override_user_id": False,
                "override_date": False,
                "override_reason": False,
            }
        )
        self._compute_scoring_values()

    # ------------------------------------------------------------------
    # Backend entry points (module specific)
    # ------------------------------------------------------------------

    @api.model
    def _get_active_sustainability_survey(self):
        return self.env["survey.survey"].search(
            [("is_sustainability", "=", True), ("active", "=", True)],
            limit=1,
        )

    @api.model
    def action_start_new_sustainability_evaluation(self):
        """Start a new Sustainability evaluation from the backend."""
        survey = self._get_active_sustainability_survey()
        if not survey:
            raise UserError(
                _(
                    "There is no active Sustainability questionnaire. "
                    "Please contact the administrator."
                )
            )
        return survey.action_start_sustainability_evaluation()

    def action_start_sustainability_from_form(self):
        """Start an evaluation from the list's 'New' form panel."""
        self.ensure_one()
        return self.action_start_new_sustainability_evaluation()

    def action_continue_sustainability_evaluation(self):
        """Resume an evaluation still in progress (new/in_progress)."""
        self.ensure_one()
        if self.state not in ("new", "in_progress"):
            raise UserError(_("This evaluation has already been completed."))
        if not self.survey_id:
            raise UserError(_("The related survey could not be found."))
        return {
            "type": "ir.actions.act_url",
            "target": "new",
            "url": "/survey/start/%s?answer_token=%s"
            % (self.survey_id.access_token, self.access_token),
        }

    # ------------------------------------------------------------------
    # Notifications and crons (module specific)
    # ------------------------------------------------------------------

    def _sustainability_evaluation_domain(self):
        return [
            ("survey_id.is_sustainability", "=", True),
            ("state", "=", "done"),
            ("test_entry", "=", False),
        ]

    @api.model
    def _cron_sustainability_retry_reminder(self):
        """Notify users whose retry cooldown ends today (sent once)."""
        evaluations = self.search(
            self._sustainability_evaluation_domain()
            + [
                ("certification_level", "=", "none"),
                ("next_attempt_date", "=", fields.Date.today()),
            ]
        )
        template = self.env.ref(
            "sustainability.mail_template_sust_retry_available",
            raise_if_not_found=False,
        )
        if not template:
            return
        for evaluation in evaluations:
            if evaluation.partner_id.email:
                template.send_mail(evaluation.id)

    @api.model
    def _cron_sustainability_renewal_reminder(self):
        """Send the renewal reminder exactly N days before expiry."""
        today = fields.Date.today()
        template = self.env.ref(
            "sustainability.mail_template_sust_renewal_due",
            raise_if_not_found=False,
        )
        if not template:
            return
        surveys = self.env["survey.survey"].search([("is_sustainability", "=", True)])
        for survey in surveys:
            reminder_days = survey.sustain_renewal_reminder_days or 30
            evaluations = self.search(
                self._sustainability_evaluation_domain()
                + [
                    ("survey_id", "=", survey.id),
                    ("certification_level", "!=", "none"),
                    ("expiry_date", "=", today + timedelta(days=reminder_days)),
                ]
            )
            for evaluation in evaluations:
                if evaluation.partner_id.email:
                    template.send_mail(evaluation.id)

    @api.model
    def _cron_sustainability_expiry_alert(self):
        """Alert the survey responsible the day after a badge expires."""
        yesterday = fields.Date.today() - timedelta(days=1)
        evaluations = self.search(
            self._sustainability_evaluation_domain()
            + [
                ("certification_level", "!=", "none"),
                ("expiry_date", "=", yesterday),
            ]
        )
        template = self.env.ref(
            "sustainability.mail_template_sust_admin_expiry_alert",
            raise_if_not_found=False,
        )
        if not template:
            return
        for evaluation in evaluations:
            if evaluation.survey_id.create_uid.email:
                template.send_mail(evaluation.id)

    def _send_sustainability_badge_notification(self):
        """Notify the user that a new badge was awarded."""
        self.ensure_one()
        if self.certification_level == "none":
            return
        template = self.env.ref(
            "sustainability.mail_template_sust_new_badge",
            raise_if_not_found=False,
        )
        if template and self.partner_id.email:
            template.send_mail(self.id, force_send=True)
