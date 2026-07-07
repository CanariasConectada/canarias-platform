# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, api, fields, models

# Certification levels shared by every model of this module.
CERTIFICATION_LEVELS = [
    ("none", "No seal"),
    ("bronze", "Bronze"),
    ("silver", "Silver"),
    ("gold", "Gold"),
]


class CertificationType(models.Model):
    """A certification vertical (e.g. Silver Economy, Sustainability).

    Everything a vertical needs is parameterized here: the survey used as
    questionnaire, the security groups that gate visibility, the scoring
    thresholds and timing rules, and the badge shown on the website.
    Adding a new vertical requires zero code: create its groups, its survey
    and one record of this model (the backend menu is created automatically).
    """

    _name = "certification.type"
    _description = "Company Certification Type"
    _order = "sequence, id"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True,
        help="Technical identifier used in website URLs and filters, "
        "e.g. 'silver' or 'sustainability'.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    survey_id = fields.Many2one(
        "survey.survey",
        string="Questionnaire",
        help="Survey used to evaluate companies for this certification.",
    )
    group_user_id = fields.Many2one(
        "res.groups",
        string="User Group",
        required=True,
        help="Internal users in this group can see the vertical's menu and "
        "run evaluations for their companies. Nothing is visible to "
        "internal users outside this group.",
    )
    group_manager_id = fields.Many2one(
        "res.groups",
        string="Manager Group",
        help="Users in this group manage every evaluation of this vertical "
        "and can override certification levels.",
    )
    # Scoring thresholds -------------------------------------------------
    max_score = fields.Float(
        default=80.0, help="Maximum reachable score of the questionnaire."
    )
    question_full_score = fields.Float(
        default=2.0,
        help="Score of a fully positive answer. Answers below this value "
        "trigger the improvement recommendations on the result page.",
    )
    bronze_min = fields.Float(
        string="Bronze Minimum", default=40.0, help="Minimum score for Bronze."
    )
    silver_min = fields.Float(
        string="Silver Minimum", default=56.0, help="Minimum score for Silver."
    )
    gold_min = fields.Float(
        string="Gold Minimum", default=71.0, help="Minimum score for Gold."
    )
    # Timing -------------------------------------------------------------
    cooldown_months = fields.Integer(
        default=3, help="Months to wait before retrying after a failed attempt."
    )
    validity_years = fields.Integer(
        default=1, help="Years the seal stays valid after being awarded."
    )
    renewal_reminder_days = fields.Integer(
        default=30, help="Days before expiry to send the renewal reminder."
    )
    # Website ------------------------------------------------------------
    badge_image = fields.Image(help="Seal image shown on the company microsite.")
    website_title = fields.Char(
        translate=True, help="Heading of the microsite certification section."
    )
    website_description = fields.Text(
        translate=True, help="Text of the microsite certification section."
    )
    # Auto-generated backend menu ----------------------------------------
    menu_id = fields.Many2one("ir.ui.menu", readonly=True, copy=False)
    action_id = fields.Many2one("ir.actions.act_window", readonly=True, copy=False)
    start_action_id = fields.Many2one("ir.actions.server", readonly=True, copy=False)

    _code_uniq = models.Constraint(
        "unique(code)", "The certification type code must be unique."
    )

    @api.model_create_multi
    def create(self, vals_list):
        types = super().create(vals_list)
        types._ensure_menu()
        types._sync_survey_link()
        return types

    def write(self, vals):
        previous_surveys = {t.id: t.survey_id for t in self}
        res = super().write(vals)
        if {"name", "group_user_id", "sequence"} & set(vals):
            self._sync_menu()
        if "survey_id" in vals:
            self._sync_survey_link(previous_surveys)
        return res

    def unlink(self):
        menus = self.menu_id
        actions = self.action_id
        start_actions = self.start_action_id
        res = super().unlink()
        menus.sudo().unlink()
        actions.sudo().unlink()
        start_actions.sudo().unlink()
        return res

    def _ensure_menu(self):
        """Create the vertical's root menu, gated to its user group only.

        The menu tree is data, not code, so a new vertical gets its backend
        entry point automatically. The root menu carries exactly the
        vertical's user group: plain internal users see nothing.
        """
        for cert_type in self:
            if cert_type.menu_id:
                continue
            action = (
                self.env["ir.actions.act_window"]
                .sudo()
                .create(cert_type._prepare_action_vals())
            )
            root_menu = (
                self.env["ir.ui.menu"].sudo().create(cert_type._prepare_menu_vals())
            )
            self.env["ir.ui.menu"].sudo().create(
                {
                    "name": _("My Evaluations"),
                    "parent_id": root_menu.id,
                    "action": "ir.actions.act_window,%d" % action.id,
                    "sequence": 10,
                }
            )
            start_action = (
                self.env["ir.actions.server"]
                .sudo()
                .create(cert_type._prepare_start_action_vals())
            )
            self.env["ir.ui.menu"].sudo().create(
                {
                    "name": _("New Evaluation"),
                    "parent_id": root_menu.id,
                    "action": "ir.actions.server,%d" % start_action.id,
                    "sequence": 20,
                }
            )
            cert_type.sudo().write(
                {
                    "menu_id": root_menu.id,
                    "action_id": action.id,
                    "start_action_id": start_action.id,
                }
            )

    def _sync_survey_link(self, previous_surveys=None):
        """Keep ``survey.certification_type_id`` aligned with ``survey_id``.

        The type is configured from its own form (``survey_id``), but the
        evaluations resolve their vertical through the inverse pointer on
        the survey, so both sides must always agree.
        """
        for cert_type in self:
            previous = (previous_surveys or {}).get(cert_type.id)
            if previous and previous != cert_type.survey_id:
                previous.sudo().certification_type_id = False
            survey = cert_type.survey_id
            if survey and survey.certification_type_id != cert_type:
                survey.sudo().certification_type_id = cert_type

    def _sync_menu(self):
        for cert_type in self.filtered("menu_id"):
            cert_type.menu_id.sudo().write(
                {
                    "name": cert_type.name,
                    "sequence": 50 + cert_type.sequence,
                    "group_ids": [(6, 0, cert_type.group_user_id.ids)],
                }
            )
            cert_type.action_id.sudo().write(
                {"name": _("%s Evaluations", cert_type.name)}
            )

    def _prepare_action_vals(self):
        self.ensure_one()
        return {
            "name": _("%s Evaluations", self.name),
            "res_model": "survey.user_input",
            "view_mode": "list,form",
            "domain": [
                ("certification_type_id", "=", self.id),
                ("test_entry", "=", False),
            ],
            "context": {"create": False, "certification_display": True},
            "help": _(
                "<p class='o_view_nocontent_smiling_face'>Welcome to %s</p>"
                "<p>Use the <b>New Evaluation</b> menu to start your first "
                "evaluation and find out whether your business qualifies "
                "for the seal.</p>",
                self.name,
            ),
        }

    def _prepare_start_action_vals(self):
        self.ensure_one()
        return {
            "name": _("New %s Evaluation", self.name),
            "model_id": self.env["ir.model"]._get_id("survey.user_input"),
            "state": "code",
            "code": "action = model.action_start_certification(%d)" % self.id,
        }

    def _prepare_menu_vals(self):
        self.ensure_one()
        return {
            "name": self.name,
            "sequence": 50 + self.sequence,
            "group_ids": [(6, 0, self.group_user_id.ids)],
            "web_icon": "company_certification,static/description/icon.png",
        }

    def _get_level_for_score(self, score):
        """Map a raw score to a certification level using the thresholds."""
        self.ensure_one()
        if score >= self.gold_min:
            return "gold"
        if score >= self.silver_min:
            return "silver"
        if score >= self.bronze_min:
            return "bronze"
        return "none"
