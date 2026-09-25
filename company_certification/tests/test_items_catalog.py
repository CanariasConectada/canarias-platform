# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""The 19.0.2.10.0 move to one catalogue, and the seeded Silver catalogue."""
from odoo.exceptions import ValidationError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestItemsCatalogMigration(CertificationCase):
    def _positive_item(self, question, label, min_score=2, icon="fa-star"):
        return self.env["certification.positive.item"].create(
            {
                "survey_id": self.survey.id,
                "question_id": question.id,
                "min_score": min_score,
                "label": label,
                "icon": icon,
            }
        )

    def test_positive_items_become_triggered_catalogue_items(self):
        item = self._positive_item(self.questions[1], "Question 1 OK", icon="bad icon")
        Highlight = self.env["certification.highlight"]

        counts = Highlight._cc_fold_positive_items()

        self.assertEqual(counts, {"folded": 0, "created": 1, "skipped": 0})
        highlight = item.migrated_highlight_id
        self.assertEqual(highlight.type_id, self.cert_type)
        self.assertEqual(highlight.question_id, self.questions[1])
        self.assertEqual(highlight.min_score, 2)
        self.assertEqual(highlight.label, "Question 1 OK")
        # An icon the new validation would reject falls back to the default.
        self.assertEqual(highlight.icon, "fa-check-circle")

    def test_an_item_on_an_already_triggered_question_is_folded(self):
        existing = self.env["certification.highlight"].create(
            {
                "type_id": self.cert_type.id,
                "label": "Designed wording",
                "question_id": self.questions[0].id,
                "min_score": 2,
            }
        )
        item = self._positive_item(self.questions[0], "Admin wording", min_score=1)

        counts = self.env["certification.highlight"]._cc_fold_positive_items()

        self.assertEqual(counts["folded"], 1)
        self.assertEqual(item.migrated_highlight_id, existing)
        # The administrator's threshold wins; the catalogue wording stays.
        self.assertEqual(existing.min_score, 1)
        self.assertEqual(existing.label, "Designed wording")

    def test_the_migration_is_idempotent(self):
        self._positive_item(self.questions[1], "Question 1 OK")
        Highlight = self.env["certification.highlight"]
        silver = self.env.ref("company_certification.certification_type_silver")
        silver.with_context(lang="en_US").amenities_title = False

        Highlight._cc_migrate_catalogue()
        snapshot = Highlight.with_context(active_test=False).search_read(
            [], ["type_id", "label", "icon", "question_id", "min_score"]
        )
        title = silver.with_context(lang="en_US").amenities_title
        second = Highlight._cc_migrate_catalogue()

        self.assertEqual(title, "What this shop offers")
        self.assertEqual(
            second,
            {
                "titles": 0,
                "seed_triggers": 0,
                "folded": 0,
                "created": 0,
                "skipped": 0,
            },
        )
        self.assertEqual(
            Highlight.with_context(active_test=False).search_read(
                [], ["type_id", "label", "icon", "question_id", "min_score"]
            ),
            snapshot,
        )

    def test_a_title_set_by_the_administrator_is_kept(self):
        silver = self.env.ref("company_certification.certification_type_silver")
        silver.with_context(lang="en_US").amenities_title = "Our own heading"

        self.env["certification.highlight"]._cc_fill_default_titles()

        self.assertEqual(
            silver.with_context(lang="en_US").amenities_title, "Our own heading"
        )

    def test_seed_links_never_overwrite_an_existing_trigger(self):
        access = self.env.ref(
            "company_certification.highlight_silver_access", raise_if_not_found=False
        )
        if not access:
            self.skipTest("seed item removed from this database")
        q3 = self.env.ref("company_certification.silver_economy_q3")
        access.write({"question_id": q3.id, "min_score": 1, "answer_ids": [(5,)]})

        self.env["certification.highlight"]._cc_link_seed_triggers()

        self.assertEqual(access.question_id, q3)

    def test_a_legacy_minimum_of_zero_becomes_the_best_score(self):
        created = self._positive_item(self.questions[1], "Any answer", min_score=0)
        existing = self.env["certification.highlight"].create(
            {
                "type_id": self.cert_type.id,
                "label": "Designed wording",
                "question_id": self.questions[0].id,
                "min_score": 1,
            }
        )
        folded = self._positive_item(self.questions[0], "Any answer", min_score=0)

        with self.assertLogs(
            "odoo.addons.company_certification.models.certification_highlight",
            level="WARNING",
        ) as logs:
            self.env["certification.highlight"]._cc_fold_positive_items()

        self.assertEqual(created.migrated_highlight_id.min_score, 2)
        self.assertEqual(folded.migrated_highlight_id, existing)
        self.assertEqual(existing.min_score, 2, "a 'No' must never trigger it")
        self.assertEqual(sum("had minimum score 0" in line for line in logs.output), 2)

    def test_best_answer_of_takes_every_answer_tied_at_the_top(self):
        question = self.env["survey.question"].create(
            {
                "survey_id": self.survey.id,
                "title": "Two top answers",
                "question_type": "simple_choice",
                "suggested_answer_ids": [
                    (0, 0, {"value": "No", "answer_score": 0}),
                    (0, 0, {"value": "Yes", "answer_score": 2}),
                    (0, 0, {"value": "Always", "answer_score": 2}),
                ],
            }
        )
        self.env["ir.model.data"].create(
            {
                "module": "company_certification",
                "name": "test_tied_question",
                "model": "survey.question",
                "res_id": question.id,
            }
        )

        values = self.env["certification.highlight"]._cc_seed_trigger_values(
            {"best_answer_of": ["test_tied_question"]}
        )

        top = question.suggested_answer_ids.filtered(lambda a: a.answer_score == 2)
        self.assertEqual(sorted(values["answer_ids"][0][2]), sorted(top.ids))

    def test_an_archived_match_gets_a_new_active_item(self):
        archived = self.env["certification.highlight"].create(
            {
                "type_id": self.cert_type.id,
                "label": "Archived wording",
                "question_id": self.questions[0].id,
                "min_score": 2,
                "active": False,
            }
        )
        item = self._positive_item(self.questions[0], "Still shown")

        counts = self.env["certification.highlight"]._cc_fold_positive_items()

        self.assertEqual(counts["created"], 1)
        self.assertNotEqual(item.migrated_highlight_id, archived)
        self.assertTrue(item.migrated_highlight_id.active)
        self.assertFalse(archived.active)


@tagged("post_install", "-at_install")
class TestTriggerGuards(CertificationCase):
    def _highlight(self, **values):
        return self.env["certification.highlight"].create(
            dict({"type_id": self.cert_type.id, "label": "Item"}, **values)
        )

    def test_an_empty_minimum_takes_the_best_answer_score(self):
        created = self._highlight(question_id=self.questions[0].id)
        self.assertEqual(created.min_score, 2)

        written = self._highlight()
        written.question_id = self.questions[1]
        self.assertEqual(written.min_score, 2)

        written.min_score = 0
        self.assertEqual(written.min_score, 2, "0 would fire on a 'No'")

    def test_an_explicit_minimum_is_kept(self):
        self.assertEqual(
            self._highlight(question_id=self.questions[0].id, min_score=1).min_score,
            1,
        )

    def test_a_multiple_choice_question_cannot_be_a_trigger_question(self):
        multiple = self.env["survey.question"].create(
            {
                "survey_id": self.survey.id,
                "title": "Pick several",
                "question_type": "multiple_choice",
                "suggested_answer_ids": [
                    (0, 0, {"value": "A", "answer_score": 1}),
                    (0, 0, {"value": "B", "answer_score": 1}),
                ],
            }
        )
        with self.assertRaises(ValidationError):
            self._highlight(question_id=multiple.id)
        # Its answers are fine as trigger answers.
        self._highlight(answer_ids=[(6, 0, multiple.suggested_answer_ids[:1].ids)])

    def test_an_unscored_question_type_never_triggers(self):
        answer = self._run_evaluation(3)
        highlight = self._highlight(question_id=self.questions[0].id)
        # Simulate a question whose type changed after the item was set up.
        self.questions[0].question_type = "multiple_choice"

        self.assertFalse(highlight._is_triggered_by(answer.user_input_line_ids))


@tagged("post_install", "-at_install")
class TestSeededSilverCatalogue(CertificationCase):
    """The Silver section must be balanced with Sostenibilidad.

    Runs on the seeded types, so it checks what a fresh database gets and
    what the migration left on an existing one.
    """

    def test_seeded_items_carry_the_triggers_of_the_single_source(self):
        """The data file and the migration both apply _CC_SEED_TRIGGERS."""
        Highlight = self.env["certification.highlight"]
        for xmlid, spec in Highlight._CC_SEED_TRIGGERS.items():
            with self.subTest(item=xmlid):
                highlight = self.env.ref("company_certification.%s" % xmlid)
                values = Highlight._cc_seed_trigger_values(spec)
                self.assertIsNotNone(values, "a question of the spec is missing")
                if "question_id" in values:
                    self.assertEqual(highlight.question_id.id, values["question_id"])
                    self.assertEqual(highlight.min_score, values["min_score"])
                else:
                    self.assertEqual(
                        highlight.answer_ids.ids, values["answer_ids"][0][2]
                    )
        # Every seeded item is covered: none is left always shown by mistake.
        seeded = self.env["ir.model.data"].search(
            [
                ("module", "=", "company_certification"),
                ("model", "=", "certification.highlight"),
            ]
        )
        self.assertEqual(set(seeded.mapped("name")), set(Highlight._CC_SEED_TRIGGERS))

    def test_signage_triggers_on_yes_to_signage_or_lighting(self):
        signage = self.env.ref("company_certification.highlight_silver_signage")
        q2 = self.env.ref("company_certification.silver_economy_q2")
        q3 = self.env.ref("company_certification.silver_economy_q3")

        self.assertFalse(signage.question_id)
        self.assertEqual(signage.answer_ids.question_id, q2 | q3)
        self.assertEqual(set(signage.answer_ids.mapped("answer_score")), {2})

    def test_silver_is_balanced_with_sustainability(self):
        silver = self.env.ref("company_certification.certification_type_silver")
        sust = self.env.ref("company_certification.certification_type_sustainability")

        self.assertGreaterEqual(len(silver.highlight_ids), 10)
        self.assertLessEqual(
            abs(len(silver.highlight_ids) - len(sust.highlight_ids)), 2
        )

    def test_a_full_silver_evaluation_renders_every_silver_item(self):
        silver = self.env.ref("company_certification.certification_type_silver")
        survey = silver.survey_id
        answer = self.env["survey.user_input"].create(
            {
                "survey_id": survey.id,
                "partner_id": self.user.partner_id.id,
                "company_id": self.company.id,
                "test_entry": False,
            }
        )
        for question in survey.question_ids.filtered(lambda q: not q.is_page):
            best = question.suggested_answer_ids.sorted("answer_score")[-1:]
            if best:
                self.env["survey.user_input.line"].create(
                    {
                        "user_input_id": answer.id,
                        "question_id": question.id,
                        "answer_type": "suggestion",
                        "suggested_answer_id": best.id,
                    }
                )
        answer._mark_done()
        self.assertTrue(
            self.company._get_valid_certifications().filtered(
                lambda st: st.type_id == silver
            )
        )

        body = self.env["ir.qweb"]._render(
            "company_certification.certification_block",
            {"cc_company": self.company},
        )

        self.assertEqual(
            str(body).count("o_cc_amenity__label"), len(silver.highlight_ids)
        )
