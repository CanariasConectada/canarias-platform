# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The icon list shown under a seal on a certified company's microsite.

One catalogue per certification type (``certification.highlight``). An item
without a trigger is always shown; an item with a trigger question or trigger
answers only when the company's awarding evaluation meets it. A seal with no
evaluation (imported) shows the whole catalogue, or only the untriggered
items when the type says so.
"""
from lxml import html

from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestCertificationAmenities(CertificationCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Highlight = cls.env["certification.highlight"]
        cls.baseline = Highlight.create(
            {
                "type_id": cls.cert_type.id,
                "label": "Acceso sin barreras",
                "description": "Entrada cómoda.",
                "icon": "fa-wheelchair",
                "sequence": 10,
            }
        )
        cls.by_score = Highlight.create(
            {
                "type_id": cls.cert_type.id,
                "label": "Question 0 well answered",
                "icon": "fa-star",
                "sequence": 20,
                "question_id": cls.questions[0].id,
                "min_score": 2,
            }
        )
        cls.yes_on_last = cls.questions[2].suggested_answer_ids.filtered(
            lambda a: a.answer_score == 2
        )
        cls.by_answer = Highlight.create(
            {
                "type_id": cls.cert_type.id,
                "label": "Yes on question 2",
                "icon": "fa-heart",
                "sequence": 30,
                "answer_ids": [(6, 0, cls.yes_on_last.ids)],
            }
        )

    def _labels(self, company=None):
        company = company or self.company
        return [
            item["label"]
            for item in company._get_certification_amenities(self.cert_type)
        ]

    def _award_imported_seal(self):
        """A seal with no user_input_id, the shape the import produced."""
        return self.env["res.company.certification"].create(
            {
                "company_id": self.company.id,
                "type_id": self.cert_type.id,
                "level": "gold",
                "score": 100,
                "expiry_date": "2099-01-01",
            }
        )

    # Rendering rules ------------------------------------------------------

    def test_a_full_evaluation_shows_baseline_and_every_triggered_item(self):
        self._run_evaluation(3)

        self.assertEqual(
            self._labels(),
            ["Acceso sin barreras", "Question 0 well answered", "Yes on question 2"],
        )

    def test_a_score_below_the_minimum_hides_the_item(self):
        # Silver level (2 of 3): question 0 and 1 "Yes", question 2 "No".
        self._run_evaluation(2)

        self.assertEqual(
            self._labels(), ["Acceso sin barreras", "Question 0 well answered"]
        )

    def test_an_answer_trigger_follows_the_selected_answer(self):
        answer = self._run_evaluation(3)
        self.assertIn("Yes on question 2", self._labels())

        line = answer.user_input_line_ids.filtered(
            lambda ln: ln.question_id == self.questions[2]
        )
        line.suggested_answer_id = self.questions[2].suggested_answer_ids.filtered(
            lambda a: a.answer_score == 0
        )

        self.assertNotIn("Yes on question 2", self._labels())

    def test_either_trigger_is_enough(self):
        self.by_answer.write({"question_id": self.questions[1].id, "min_score": 2})
        # Question 1 "Yes", question 2 "No": the question trigger alone holds.
        self._run_evaluation(2)

        self.assertIn("Yes on question 2", self._labels())

    def test_baseline_items_show_whatever_was_answered(self):
        self._run_evaluation(2)
        self.company.certification_ids.user_input_id.user_input_line_ids.unlink()

        self.assertEqual(self._labels(), ["Acceso sin barreras"])

    def test_archived_items_are_not_shown(self):
        self._run_evaluation(3)
        self.by_score.active = False

        self.assertNotIn("Question 0 well answered", self._labels())

    def test_items_follow_their_sequence(self):
        self.by_answer.sequence = 1
        self._run_evaluation(3)

        self.assertEqual(self._labels()[0], "Yes on question 2")

    # Seals without an evaluation -----------------------------------------

    def test_an_imported_seal_shows_the_whole_catalogue_by_default(self):
        self.assertTrue(self.cert_type.show_all_without_evaluation)
        self._award_imported_seal()

        self.assertEqual(
            self._labels(),
            ["Acceso sin barreras", "Question 0 well answered", "Yes on question 2"],
        )

    def test_an_imported_seal_can_show_only_the_baseline(self):
        self.cert_type.show_all_without_evaluation = False
        self._award_imported_seal()

        self.assertEqual(self._labels(), ["Acceso sin barreras"])

    def test_a_company_without_the_seal_gets_no_items(self):
        # The list is made of public claims: an uncertified shop shows none.
        self.assertEqual(self._labels(), [])

    def test_every_amenity_carries_the_keys_the_template_reads(self):
        """The template reads ``icon`` and ``label`` unconditionally."""
        self._run_evaluation(3)

        for item in self.company._get_certification_amenities(self.cert_type):
            self.assertEqual(set(item), {"label", "description", "icon"})

    # Catalogue integrity --------------------------------------------------

    def test_icon_must_be_a_font_awesome_class(self):
        for bad in ("wheelchair", "fa fa-wheelchair", 'fa-x" onclick="y', "FA-X"):
            with self.subTest(icon=bad), self.assertRaises(ValidationError):
                self.baseline.icon = bad
        self.baseline.icon = "fa-hand-paper-o"
        self.assertIn('class="fa fa-lg fa-hand-paper-o"', self.baseline.icon_preview)

    def test_triggers_must_come_from_the_type_questionnaire(self):
        other = self.env["survey.survey"].create({"title": "Other"})
        question = self.env["survey.question"].create(
            {"survey_id": other.id, "title": "Elsewhere", "question_type": "text_box"}
        )
        with self.assertRaises(ValidationError):
            self.baseline.question_id = question

    def test_is_baseline_reflects_the_triggers(self):
        self.assertTrue(self.baseline.is_baseline)
        self.assertFalse(self.by_score.is_baseline)
        self.assertFalse(self.by_answer.is_baseline)

    # Template -------------------------------------------------------------

    def test_the_seal_block_renders_one_icon_per_shown_item(self):
        self._run_evaluation(2)

        body = self.env["ir.qweb"]._render(
            "company_certification.certification_block",
            {"cc_company": self.company},
        )
        tree = html.fromstring(str(body))

        icons = tree.xpath("//i[contains(@class, 'o_cc_amenity__icon')]")
        self.assertEqual(
            [icon.get("class").split()[1] for icon in icons],
            ["fa-wheelchair", "fa-star"],
        )
