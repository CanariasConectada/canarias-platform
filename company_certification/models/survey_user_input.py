# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .certification_type import CERTIFICATION_LEVELS

# Fields that impact the company certification status when they change.
_STATUS_TRIGGER_FIELDS = (
    "state",
    "certification_level",
    "expiry_date",
    "survey_id",
    "company_id",
    "test_entry",
    "manual_certification_level",
    "is_manually_overridden",
)


class SurveyUserInput(models.Model):
    _inherit = "survey.user_input"

    company_id = fields.Many2one(
        "res.company",
        string="Evaluated Company",
        index=True,
        help="Company this evaluation belongs to.",
    )
    certification_type_id = fields.Many2one(
        related="survey_id.certification_type_id",
        store=True,
        index=True,
    )
    certification_level = fields.Selection(
        CERTIFICATION_LEVELS,
        compute="_compute_certification_level",
        store=True,
    )
    next_attempt_date = fields.Date(
        compute="_compute_next_attempt_date",
        store=True,
        help="Date from which the company may run a new evaluation.",
    )
    expiry_date = fields.Date(
        compute="_compute_expiry_date",
        store=True,
        help="Date the awarded seal expires.",
    )
    # Manual override audit trail -----------------------------------------
    is_manually_overridden = fields.Boolean(
        help="A manager overrode the computed certification level."
    )
    manual_certification_level = fields.Selection(
        CERTIFICATION_LEVELS, string="Overridden Level"
    )
    override_user_id = fields.Many2one("res.users", string="Overridden By")
    override_date = fields.Datetime()
    override_reason = fields.Text()

    # ------------------------------------------------------------------
    # Computes
    # ------------------------------------------------------------------
    @api.depends(
        "scoring_total",
        "certification_type_id",
        "is_manually_overridden",
        "manual_certification_level",
    )
    def _compute_certification_level(self):
        for user_input in self:
            cert_type = user_input.certification_type_id
            if not cert_type or user_input.survey_id.scoring_type == "no_scoring":
                user_input.certification_level = "none"
            elif user_input.is_manually_overridden:
                user_input.certification_level = (
                    user_input.manual_certification_level or "none"
                )
            else:
                user_input.certification_level = cert_type._get_level_for_score(
                    user_input.scoring_total
                )

    @api.depends("create_date", "certification_level", "state")
    def _compute_next_attempt_date(self):
        for user_input in self:
            cert_type = user_input.certification_type_id
            if user_input.state != "done" or not cert_type:
                user_input.next_attempt_date = False
                continue
            start = fields.Date.to_date(user_input.create_date)
            if user_input.certification_level == "none":
                delta = relativedelta(months=cert_type.cooldown_months or 3)
            else:
                delta = relativedelta(years=cert_type.validity_years or 1)
            user_input.next_attempt_date = start + delta

    @api.depends("create_date", "certification_level", "state")
    def _compute_expiry_date(self):
        for user_input in self:
            cert_type = user_input.certification_type_id
            if (
                user_input.state != "done"
                or not cert_type
                or user_input.certification_level == "none"
            ):
                user_input.expiry_date = False
            else:
                user_input.expiry_date = fields.Date.to_date(
                    user_input.create_date
                ) + relativedelta(years=cert_type.validity_years or 1)

    def _get_certification_level_label(self):
        """Translated label of the level, for QWeb templates."""
        self.ensure_one()
        selection = self._fields["certification_level"]._description_selection(self.env)
        return dict(selection).get(self.certification_level, "")

    # ------------------------------------------------------------------
    # Company status synchronization
    # ------------------------------------------------------------------
    def _refresh_company_certification(self):
        status_model = self.env["res.company.certification"]
        pairs = {
            (ui.company_id, ui.certification_type_id)
            for ui in self
            if ui.company_id and ui.certification_type_id
        }
        for company, cert_type in pairs:
            status_model._refresh(company, cert_type)

    def _mark_done(self):
        res = super()._mark_done()
        self.env.flush_all()
        self._refresh_company_certification()
        for user_input in self.filtered(
            lambda ui: ui.certification_type_id
            and not ui.test_entry
            and ui.certification_level != "none"
        ):
            user_input._send_new_badge_notification()
        return res

    def write(self, vals):
        # Stamp the audit trail when a manager toggles the manual override
        # from the form view without going through action_override_level().
        if (
            "manual_certification_level" in vals or "is_manually_overridden" in vals
        ) and "override_user_id" not in vals:
            vals = dict(
                vals,
                override_user_id=self.env.user.id,
                override_date=fields.Datetime.now(),
            )
        res = super().write(vals)
        if set(vals) & set(_STATUS_TRIGGER_FIELDS):
            self._refresh_company_certification()
        return res

    def unlink(self):
        pairs = {
            (ui.company_id, ui.certification_type_id)
            for ui in self
            if ui.company_id and ui.certification_type_id
        }
        res = super().unlink()
        status_model = self.env["res.company.certification"]
        for company, cert_type in pairs:
            status_model._refresh(company, cert_type)
        return res

    # ------------------------------------------------------------------
    # Manual override (managers only)
    # ------------------------------------------------------------------
    def _check_certification_manager(self):
        self.ensure_one()
        group = self.certification_type_id.group_manager_id
        is_manager = group and group in self.env.user.all_group_ids
        if not is_manager and not self.env.user.has_group(
            "company_certification.group_certification_manager"
        ):
            raise UserError(_("Only certification managers can override levels."))

    def action_override_level(self, level, reason=False):
        """Override the computed certification level, keeping an audit trail."""
        self.ensure_one()
        self._check_certification_manager()
        self.write(
            {
                "is_manually_overridden": True,
                "manual_certification_level": level,
                "override_user_id": self.env.user.id,
                "override_date": fields.Datetime.now(),
                "override_reason": reason,
            }
        )

    def action_reset_override(self):
        """Restore the level computed from the score."""
        self.ensure_one()
        self._check_certification_manager()
        if not self.is_manually_overridden:
            return
        self.write(
            {
                "is_manually_overridden": False,
                "manual_certification_level": False,
                "override_user_id": False,
                "override_date": False,
                "override_reason": False,
            }
        )

    # ------------------------------------------------------------------
    # Evaluation start / continue
    # ------------------------------------------------------------------
    @api.model
    def _get_last_done_attempt(self, cert_type, company):
        return self.sudo().search(
            [
                ("certification_type_id", "=", cert_type.id),
                ("company_id", "=", company.id),
                ("state", "=", "done"),
                ("test_entry", "=", False),
            ],
            order="create_date desc",
            limit=1,
        )

    @api.model
    def _start_certification_evaluation(self, cert_type):
        """Cooldown-check and create a real evaluation for the current user.

        Returns the survey URL to redirect to. Raises UserError when the
        user has no company, the vertical has no active survey, or the
        cooldown of the last attempt is still running.
        """
        user = self.env.user
        if not user.company_id:
            raise UserError(
                _("You need a company on your user profile to run an evaluation.")
            )
        survey = cert_type.survey_id
        if not survey or not survey.active:
            raise UserError(
                _(
                    "No questionnaire is configured for %s. "
                    "Please contact the administrator.",
                    cert_type.name,
                )
            )
        last = self._get_last_done_attempt(cert_type, user.company_id)
        if (
            last
            and last.next_attempt_date
            and last.next_attempt_date > fields.Date.today()
        ):
            raise UserError(
                _("You cannot run a new evaluation until %s.", last.next_attempt_date)
            )
        answer = self.sudo().create(
            {
                "survey_id": survey.id,
                "partner_id": user.partner_id.id,
                "company_id": user.company_id.id,
                "test_entry": False,
            }
        )
        return "/survey/start/%s?answer_token=%s" % (
            survey.access_token,
            answer.access_token,
        )

    @api.model
    def action_start_certification(self, cert_type_id):
        """Entry point of the auto-generated 'New Evaluation' menu item."""
        cert_type = self.env["certification.type"].browse(cert_type_id)
        if not cert_type.exists():
            raise UserError(_("Unknown certification type."))
        url = self._start_certification_evaluation(cert_type)
        return {"type": "ir.actions.act_url", "target": "new", "url": url}

    def action_continue_certification_evaluation(self):
        """Resume an evaluation still in progress."""
        self.ensure_one()
        if self.state not in ("new", "in_progress"):
            raise UserError(_("This evaluation is already completed."))
        return {
            "type": "ir.actions.act_url",
            "target": "new",
            "url": "/survey/start/%s?answer_token=%s"
            % (self.survey_id.access_token, self.access_token),
        }

    # ------------------------------------------------------------------
    # Notifications and crons
    # ------------------------------------------------------------------
    def _send_new_badge_notification(self):
        self.ensure_one()
        template = self.env.ref(
            "company_certification.mail_template_certification_new_badge",
            raise_if_not_found=False,
        )
        if template and self.partner_id.email:
            template.send_mail(self.id, force_send=True)

    @api.model
    def _cron_certification_retry_reminder(self):
        """Remind users whose retry cooldown has just elapsed."""
        today = fields.Date.today()
        evaluations = self.search(
            [
                ("certification_type_id", "!=", False),
                ("certification_level", "=", "none"),
                ("state", "=", "done"),
                ("test_entry", "=", False),
                ("next_attempt_date", "=", today),
            ]
        )
        template = self.env.ref(
            "company_certification.mail_template_certification_retry_available",
            raise_if_not_found=False,
        )
        if template:
            for evaluation in evaluations.filtered(lambda e: e.partner_id.email):
                template.send_mail(evaluation.id, force_send=True)

    @api.model
    def _cron_certification_renewal_reminder(self):
        """Remind holders shortly before their seal expires."""
        today = fields.Date.today()
        template = self.env.ref(
            "company_certification.mail_template_certification_renewal_due",
            raise_if_not_found=False,
        )
        if not template:
            return
        for cert_type in self.env["certification.type"].search([]):
            reminder_date = today + timedelta(
                days=cert_type.renewal_reminder_days or 30
            )
            evaluations = self.search(
                [
                    ("certification_type_id", "=", cert_type.id),
                    ("certification_level", "!=", "none"),
                    ("state", "=", "done"),
                    ("test_entry", "=", False),
                    ("expiry_date", "=", reminder_date),
                ]
            )
            for evaluation in evaluations.filtered(lambda e: e.partner_id.email):
                template.send_mail(evaluation.id, force_send=True)

    @api.model
    def _cron_certification_expiry(self):
        """Drop expired company statuses and alert the survey manager."""
        today = fields.Date.today()
        expired_statuses = self.env["res.company.certification"].search(
            [("expiry_date", "<", today)]
        )
        template = self.env.ref(
            "company_certification.mail_template_certification_expiry_alert",
            raise_if_not_found=False,
        )
        for status in expired_statuses:
            evaluation = status.user_input_id
            if template and evaluation and evaluation.survey_id.user_id.email:
                template.send_mail(evaluation.id, force_send=True)
        expired_statuses.unlink()
