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

    sustain_certification_level = fields.Selection(
        [
            ("none", "No badge"),
            ("bronze", "Bronze"),
            ("silver", "Silver"),
            ("gold", "Gold"),
        ],
        string="Sustainability Level",
        compute="_compute_sustain_certification",
        store=True,
    )
    sustain_certification_date = fields.Date(
        string="Sustainability Certification Date",
        compute="_compute_sustain_certification",
        store=True,
    )
    sustain_expiry_date = fields.Date(
        string="Sustainability Badge Expiry",
        compute="_compute_sustain_certification",
        store=True,
    )
    sustain_cert_score = fields.Float(
        string="Sustainability Score (%)",
        compute="_compute_sustain_certification",
        store=True,
    )
    sustain_evaluation_count = fields.Integer(
        string="Sustainability Evaluations",
        compute="_compute_sustain_evaluation_count",
    )

    def _get_last_sustainability_certification(self):
        """Return the most recent awarded Sustainability evaluation.

        Uses ``sudo()`` because it also runs in public website context.
        """
        self.ensure_one()
        return (
            self.env["survey.user_input"]
            .sudo()
            .search(
                [
                    ("company_id", "=", self.id),
                    ("survey_id.is_sustainability", "=", True),
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
        "certification_input_ids.survey_id.is_sustainability",
    )
    def _compute_sustain_certification(self):
        """Compute the current (non expired) Sustainability badge."""
        today = fields.Date.today()
        for company in self:
            last_cert = company._get_last_sustainability_certification()
            if last_cert and last_cert.expiry_date and last_cert.expiry_date >= today:
                company.sustain_certification_level = last_cert.certification_level
                company.sustain_certification_date = last_cert.create_date.date()
                company.sustain_expiry_date = last_cert.expiry_date
                company.sustain_cert_score = last_cert.scoring_percentage
            else:
                company.sustain_certification_level = "none"
                company.sustain_certification_date = False
                company.sustain_expiry_date = False
                company.sustain_cert_score = 0.0

    def _compute_sustain_evaluation_count(self):
        for company in self:
            company.sustain_evaluation_count = self.env[
                "survey.user_input"
            ].search_count(
                [
                    ("survey_id.is_sustainability", "=", True),
                    ("company_id", "=", company.id),
                    ("test_entry", "=", False),
                ]
            )

    def action_open_sustainability_evaluations(self):
        """Open the list of Sustainability evaluations of this company."""
        self.ensure_one()
        return {
            "name": _("Sustainability Evaluations - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "survey.user_input",
            "view_mode": "list,form",
            "domain": [
                ("survey_id.is_sustainability", "=", True),
                ("company_id", "=", self.id),
                ("test_entry", "=", False),
            ],
            "context": {"create": False},
        }

    def _get_sustainability_positive_items(self):
        """Return the positive items of the last valid evaluation.

        Each item is a dict ``{"label": str, "icon": str}`` rendered on the
        public microsite. The three items are matched heuristically against
        the questionnaire titles (energy, waste, eco/local products).
        """
        self.ensure_one()
        last_cert = self._get_last_sustainability_certification()
        if (
            not last_cert
            or not last_cert.expiry_date
            or last_cert.expiry_date < fields.Date.today()
        ):
            return []

        lines = last_cert.user_input_line_ids
        questions = last_cert.survey_id.question_ids
        item_specs = [
            (
                lambda title: "energ" in title,
                _("We apply energy saving practices"),
                "fa-bolt",
            ),
            (
                lambda title: "residuo" in title,
                _("We manage our waste responsibly"),
                "fa-recycle",
            ),
            (
                lambda title: "ecológ" in title
                or "local" in title
                or "comunidad" in title,
                _("We offer eco-friendly and/or local products"),
                "fa-leaf",
            ),
        ]
        items = []
        for matcher, label, icon in item_specs:
            question = questions.filtered(
                lambda q, matcher=matcher: matcher((q.title or "").lower())
            )
            if not question:
                continue
            line = lines.filtered(
                lambda line, question=question: line.question_id == question[0]
            )
            if line and line.answer_score >= 1:
                items.append({"label": label, "icon": icon})
        return items
