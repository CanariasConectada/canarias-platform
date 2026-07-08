# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models

from .certification_type import CERTIFICATION_LEVELS


class ResCompanyCertification(models.Model):
    """Current certification status of a company for one vertical.

    One record per (company, certification type) pair, kept in sync from the
    evaluations (``survey.user_input``). A record only exists while the
    company holds a seal; it is removed when no valid evaluation remains.
    Stored so the website directory and backend filters can search it.
    """

    _name = "res.company.certification"
    _description = "Company Certification Status"
    _order = "company_id, type_id"

    company_id = fields.Many2one(
        "res.company", required=True, ondelete="cascade", index=True
    )
    type_id = fields.Many2one(
        "certification.type", required=True, ondelete="cascade", index=True
    )
    level = fields.Selection(CERTIFICATION_LEVELS, required=True, default="none")
    certification_date = fields.Date()
    expiry_date = fields.Date()
    score = fields.Float(help="Score of the awarding evaluation.")
    user_input_id = fields.Many2one(
        "survey.user_input", string="Awarding Evaluation", ondelete="set null"
    )

    _company_type_uniq = models.Constraint(
        "unique(company_id, type_id)",
        "A company can only have one status per certification type.",
    )

    def _get_level_label(self):
        """Translated label of the level, for QWeb templates."""
        self.ensure_one()
        selection = self._fields["level"]._description_selection(self.env)
        return dict(selection).get(self.level, "")

    def _is_valid(self):
        self.ensure_one()
        return (
            self.level != "none"
            and self.expiry_date
            and self.expiry_date >= fields.Date.today()
        )

    def _refresh(self, company, cert_type):
        """Recompute the status record of ``(company, cert_type)``.

        Looks up the newest awarding evaluation still in force and upserts
        the status record accordingly; drops the record when the company no
        longer holds a valid seal. Runs as sudo: it is triggered by regular
        users completing evaluations, who have no access to this model.
        """
        status_model = self.sudo()
        awarding = (
            self.env["survey.user_input"]
            .sudo()
            .search(
                [
                    ("company_id", "=", company.id),
                    ("certification_type_id", "=", cert_type.id),
                    ("state", "=", "done"),
                    ("test_entry", "=", False),
                    ("certification_level", "!=", "none"),
                ],
                order="create_date desc",
                limit=1,
            )
        )
        record = status_model.search(
            [("company_id", "=", company.id), ("type_id", "=", cert_type.id)]
        )
        valid = (
            awarding
            and awarding.expiry_date
            and awarding.expiry_date >= fields.Date.today()
        )
        if not valid:
            record.unlink()
            return status_model.browse()
        vals = {
            "company_id": company.id,
            "type_id": cert_type.id,
            "level": awarding.certification_level,
            "certification_date": fields.Date.to_date(awarding.create_date),
            "expiry_date": awarding.expiry_date,
            "score": awarding.scoring_percentage,
            "user_input_id": awarding.id,
        }
        if record:
            record.write(vals)
            return record
        return status_model.create(vals)
