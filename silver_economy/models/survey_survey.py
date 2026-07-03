# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, fields, models
from odoo.exceptions import UserError


class SurveySurvey(models.Model):
    _inherit = "survey.survey"

    is_silver_economy = fields.Boolean(
        string="Is Silver Economy Evaluation",
        default=False,
        help="If checked, this survey is used for Silver Economy certification",
    )
    # Generic flag shared with any sibling certification module (e.g.
    # sustainability). Both modules define this field and its compute with the
    # same name and a cooperative body, so whichever implementation wins in
    # the registry MRO produces the right value for every survey type.
    is_certification_survey = fields.Boolean(
        string="Is Certification Survey",
        compute="_compute_is_certification_survey",
    )

    # Configurable score thresholds
    silver_max_score = fields.Float(
        string="Maximum Score",
        default=80.0,
        help="Maximum reachable score (40 questions x 2 points)",
    )
    silver_bronze_min = fields.Float(
        string="Bronze Minimum",
        default=40.0,
        help="Minimum score to be awarded the Bronze badge",
    )
    silver_silver_min = fields.Float(
        string="Silver Minimum",
        default=56.0,
        help="Minimum score to be awarded the Silver badge",
    )
    silver_gold_min = fields.Float(
        string="Gold Minimum",
        default=71.0,
        help="Minimum score to be awarded the Gold badge",
    )

    # Configurable timing
    silver_cooldown_months = fields.Integer(
        string="Cooldown Months After Failing",
        default=3,
        help="Months the company must wait before retrying after a failed evaluation",
    )
    silver_validity_years = fields.Integer(
        string="Badge Validity (Years)",
        default=1,
        help="Years the badge remains valid once awarded",
    )
    silver_renewal_reminder_days = fields.Integer(
        string="Renewal Reminder Days",
        default=30,
        help="Days before expiry to send the renewal reminder",
    )

    positive_item_ids = fields.One2many(
        "silver.positive.item",
        "survey_id",
        string="Positive Items",
        help="Items shown on the microsite when the related question "
        "scores at least its minimum",
    )

    def _compute_is_certification_survey(self):
        # Cooperative body: chain into the sibling certification module when
        # it is installed, then OR our own flag on top.
        parent = super()
        if hasattr(parent, "_compute_is_certification_survey"):
            parent._compute_is_certification_survey()
        else:
            for survey in self:
                survey.is_certification_survey = False
        for survey in self:
            survey.is_certification_survey = (
                survey.is_certification_survey or survey.is_silver_economy
            )

    def _get_certification_config(self):
        """Return the certification parameters that apply to this survey.

        Cooperative hook: every certification module contributes its own
        configuration when the survey carries its flag, and delegates to the
        sibling module (if installed) otherwise. Returns ``None`` for surveys
        that are not certification surveys.
        """
        self.ensure_one()
        parent = super()
        config = (
            parent._get_certification_config()
            if hasattr(parent, "_get_certification_config")
            else None
        )
        if config is None and self.is_silver_economy:
            config = {
                "max_score": self.silver_max_score,
                "bronze_min": self.silver_bronze_min,
                "silver_min": self.silver_silver_min,
                "gold_min": self.silver_gold_min,
                "cooldown_months": self.silver_cooldown_months or 3,
                "validity_years": self.silver_validity_years or 1,
                "reminder_days": self.silver_renewal_reminder_days or 30,
                "manager_group": "silver_economy.group_silver_manager",
            }
        return config

    def action_start_silver_evaluation(self):
        """Start a real (non test) evaluation for the current internal user."""
        self.ensure_one()
        if not self.is_silver_economy:
            raise UserError(
                _("This survey is not configured as a Silver Economy evaluation.")
            )
        answer = self.env["survey.user_input"]._create_certification_answer(self)
        return {
            "type": "ir.actions.act_url",
            "name": _("Start Silver Economy evaluation"),
            "target": "new",
            "url": "/survey/start/%s?answer_token=%s"
            % (self.access_token, answer.access_token),
        }
