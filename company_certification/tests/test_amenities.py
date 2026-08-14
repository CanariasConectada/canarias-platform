# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The icon list shown under a seal on a certified company's microsite.

Two sources feed it, and which one wins is the whole point: what the company
itself scored well on when there is an evaluation, and the vertical's curated
highlights when there is not. Seals imported from the previous platform have
no evaluation at all, so without the fallback their microsites show a seal
with nothing explaining it.
"""
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestCertificationAmenities(CertificationCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.highlight = cls.env["certification.highlight"].create(
            {
                "type_id": cls.cert_type.id,
                "label": "Acceso sin barreras",
                "description": "Entrada cómoda.",
                "icon": "fa-wheelchair",
            }
        )

    def _award_imported_seal(self):
        """A seal with no user_input_id, the shape the import produced."""
        return self.env["res.company.certification"].create(
            {
                "company_id": self.user.company_id.id,
                "type_id": self.cert_type.id,
                "level": "gold",
                "score": 100,
                "expiry_date": "2099-01-01",
            }
        )

    def test_imported_seal_falls_back_to_the_vertical_highlights(self):
        self._award_imported_seal()

        amenities = self.user.company_id._get_certification_amenities(self.cert_type)

        self.assertEqual(
            amenities,
            [
                {
                    "label": "Acceso sin barreras",
                    "description": "Entrada cómoda.",
                    "icon": "fa-wheelchair",
                }
            ],
        )

    def test_highlights_follow_their_sequence(self):
        self.highlight.sequence = 20
        self.env["certification.highlight"].create(
            {
                "type_id": self.cert_type.id,
                "label": "Atención sin prisas",
                "icon": "fa-clock-o",
                "sequence": 10,
            }
        )
        self._award_imported_seal()

        amenities = self.user.company_id._get_certification_amenities(self.cert_type)

        self.assertEqual(
            [item["label"] for item in amenities],
            ["Atención sin prisas", "Acceso sin barreras"],
        )

    def test_an_earned_highlight_wins_over_the_curated_one(self):
        answer = self._run_evaluation(3)
        self.env["certification.positive.item"].create(
            {
                "survey_id": self.survey.id,
                "question_id": self.questions[0].id,
                "min_score": 1,
                "label": "Lo que este comercio hace bien",
                "icon": "fa-star",
            }
        )

        amenities = answer.company_id._get_certification_amenities(self.cert_type)

        self.assertEqual(
            [item["label"] for item in amenities],
            ["Lo que este comercio hace bien"],
            "the company's own result replaces the generic list, never both",
        )

    def test_every_amenity_carries_the_keys_the_template_reads(self):
        """Both sources must hand the template one shape.

        The template reads ``icon`` and ``label`` unconditionally; a missing
        key is a render-time KeyError on a public page, not a blank line.
        """
        answer = self._run_evaluation(3)
        self.env["certification.positive.item"].create(
            {
                "survey_id": self.survey.id,
                "question_id": self.questions[0].id,
                "min_score": 1,
                "label": "Earned",
            }
        )
        earned = answer.company_id._get_certification_amenities(self.cert_type)

        for item in earned:
            self.assertEqual(set(item), {"label", "description", "icon"})

    def test_a_company_without_the_seal_gets_no_highlights(self):
        # The fallback is keyed to holding the seal; an uncertified shop must
        # not display the vertical's promises.
        amenities = self.user.company_id._get_certification_amenities(self.cert_type)

        self.assertEqual(amenities, [])
