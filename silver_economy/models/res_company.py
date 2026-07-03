# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import _, api, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    # Shared inverse of survey.user_input.company_id; defined identically by
    # every certification module so the company badges recompute automatically
    # whenever an evaluation is created, modified or deleted.
    certification_input_ids = fields.One2many(
        "survey.user_input",
        "company_id",
        string="Certification Evaluations",
    )

    silver_certification_level = fields.Selection(
        [
            ("none", "No badge"),
            ("bronze", "Bronze"),
            ("silver", "Silver"),
            ("gold", "Gold"),
        ],
        string="Silver Economy Level",
        compute="_compute_silver_certification",
        store=True,
    )
    silver_certification_date = fields.Date(
        string="Silver Certification Date",
        compute="_compute_silver_certification",
        store=True,
    )
    silver_expiry_date = fields.Date(
        string="Silver Badge Expiry",
        compute="_compute_silver_certification",
        store=True,
    )
    silver_cert_score = fields.Float(
        string="Silver Economy Score (%)",
        compute="_compute_silver_certification",
        store=True,
    )
    silver_evaluation_count = fields.Integer(
        string="Silver Evaluations",
        compute="_compute_silver_evaluation_count",
    )

    def _get_last_silver_certification(self):
        """Return the most recent awarded Silver evaluation of the company.

        Uses ``sudo()`` because it also runs in public website context.
        """
        self.ensure_one()
        return (
            self.env["survey.user_input"]
            .sudo()
            .search(
                [
                    ("company_id", "=", self.id),
                    ("survey_id.is_silver_economy", "=", True),
                    ("state", "=", "done"),
                    ("test_entry", "=", False),
                    ("certification_level", "!=", "none"),
                ],
                order="create_date desc",
                limit=1,
            )
        )

    @api.depends(
        "certification_input_ids.certification_level",
        "certification_input_ids.state",
        "certification_input_ids.test_entry",
        "certification_input_ids.expiry_date",
        "certification_input_ids.scoring_percentage",
        "certification_input_ids.survey_id.is_silver_economy",
    )
    def _compute_silver_certification(self):
        """Compute the current (non expired) Silver badge of the company."""
        today = fields.Date.today()
        for company in self:
            last_cert = company._get_last_silver_certification()
            if last_cert and last_cert.expiry_date and last_cert.expiry_date >= today:
                company.silver_certification_level = last_cert.certification_level
                company.silver_certification_date = last_cert.create_date.date()
                company.silver_expiry_date = last_cert.expiry_date
                company.silver_cert_score = last_cert.scoring_percentage
            else:
                company.silver_certification_level = "none"
                company.silver_certification_date = False
                company.silver_expiry_date = False
                company.silver_cert_score = 0.0

    def _compute_silver_evaluation_count(self):
        for company in self:
            company.silver_evaluation_count = self.env[
                "survey.user_input"
            ].search_count(
                [
                    ("survey_id.is_silver_economy", "=", True),
                    ("company_id", "=", company.id),
                    ("test_entry", "=", False),
                ]
            )

    def action_open_silver_evaluations(self):
        """Open the list of Silver Economy evaluations of this company."""
        self.ensure_one()
        return {
            "name": _("Silver Economy Evaluations - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "survey.user_input",
            "view_mode": "list,form",
            "domain": [
                ("survey_id.is_silver_economy", "=", True),
                ("company_id", "=", self.id),
                ("test_entry", "=", False),
            ],
            "context": {"create": False},
        }

    def _get_silver_positive_items(self):
        """Return the positive items of the last valid evaluation.

        Each item is a dict ``{"label": str, "icon": str}`` rendered on the
        public microsite.
        """
        self.ensure_one()
        last_cert = self._get_last_silver_certification()
        if (
            not last_cert
            or not last_cert.expiry_date
            or last_cert.expiry_date < fields.Date.today()
        ):
            return []
        survey = last_cert.survey_id
        lines = last_cert.user_input_line_ids
        active_items = []
        for item_config in survey.positive_item_ids.sorted("sequence"):
            line = lines.filtered(
                lambda line: line.question_id == item_config.question_id
            )
            if line and line.answer_score >= item_config.min_score:
                active_items.append(
                    {
                        "label": item_config.label,
                        "icon": item_config.icon or "fa-check-circle",
                    }
                )
        return active_items
