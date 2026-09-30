# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    certification_ids = fields.One2many(
        "res.company.certification",
        "company_id",
        string="Certifications",
    )
    certification_evaluation_count = fields.Integer(
        compute="_compute_certification_evaluation_count"
    )

    def _compute_certification_evaluation_count(self):
        # Single grouped query instead of one search_count per company.
        counts = dict(
            self.env["survey.user_input"]._read_group(
                domain=[
                    ("certification_type_id", "!=", False),
                    ("company_id", "in", self.ids),
                    ("test_entry", "=", False),
                ],
                groupby=["company_id"],
                aggregates=["__count"],
            )
        )
        for company in self:
            company.certification_evaluation_count = counts.get(company, 0)

    def action_open_certification_evaluations(self):
        self.ensure_one()
        return {
            "name": _("Certification Evaluations - %s", self.name),
            "type": "ir.actions.act_window",
            "res_model": "survey.user_input",
            "view_mode": "list,form",
            "domain": [
                ("certification_type_id", "!=", False),
                ("company_id", "=", self.id),
                ("test_entry", "=", False),
            ],
            "context": {"create": False},
        }

    def _get_valid_certifications(self):
        """Certification status records currently in force for the company.

        Uses sudo because it is called from public website rendering.
        """
        self.ensure_one()
        return self.sudo().certification_ids.filtered(lambda c: c._is_valid())

    def _get_certification_amenities(self, cert_type):
        """The icon list shown under a seal on the company microsite.

        The list is the type's catalogue (``certification.highlight``)
        filtered by the company's awarding evaluation:

        * baseline items (no trigger) are always shown;
        * triggered items are shown when the evaluation meets their trigger
          (score on a question, or one of the selected answers).

        A seal with no evaluation behind it (imported from the previous
        platform) cannot meet any trigger. It shows the whole catalogue when
        the type's ``show_all_without_evaluation`` is set, which keeps what
        those microsites always showed, and only the baseline items
        otherwise.

        Sudo: rendered in public website context.
        """
        self.ensure_one()
        # Guarded rather than relying on the caller: the template only reaches
        # here inside a loop over held seals, but the list is made of public
        # claims and must never be readable for a shop that has none.
        status = self._get_valid_certifications().filtered(
            lambda st: st.type_id == cert_type
        )
        if not status:
            return []
        cert_type = cert_type.sudo()
        highlights = cert_type.highlight_ids.sorted(lambda h: (h.sequence, h.id))
        awarding = status.user_input_id[:1]
        if not awarding:
            if not cert_type.show_all_without_evaluation:
                highlights = highlights.filtered(lambda h: h._is_baseline())
            return [highlight._to_amenity() for highlight in highlights]
        lines = awarding.user_input_line_ids
        return [
            highlight._to_amenity()
            for highlight in highlights
            if highlight._is_baseline() or highlight._is_triggered_by(lines)
        ]
