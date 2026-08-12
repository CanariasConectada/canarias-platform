# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestCertificationFlow(CertificationCase):
    def test_level_thresholds(self):
        """Scores map to levels through the type thresholds."""
        # yes_answers -> score = yes_answers * 2
        cases = [(0, "none"), (1, "bronze"), (2, "silver"), (3, "gold")]
        for yes_answers, expected in cases:
            answer = self._run_evaluation(yes_answers)
            self.assertEqual(
                answer.certification_level,
                expected,
                "Score %s should give %s" % (yes_answers * 2, expected),
            )
            answer.unlink()

    def test_company_status_created_and_dropped(self):
        """An awarding evaluation upserts the company status record."""
        answer = self._run_evaluation(3)
        status = self.company.certification_ids
        self.assertEqual(len(status), 1)
        self.assertEqual(status.type_id, self.cert_type)
        self.assertEqual(status.level, "gold")
        self.assertEqual(status.user_input_id, answer)
        self.assertTrue(status._is_valid())
        # Removing the evaluation drops the status record.
        answer.unlink()
        self.assertFalse(self.company.certification_ids)

    def test_failed_evaluation_creates_no_status(self):
        self._run_evaluation(0)  # score 0 < bronze_min 2
        self.assertFalse(self.company.certification_ids)

    def test_expiry_and_next_attempt_dates(self):
        answer = self._run_evaluation(3)
        start = fields.Date.to_date(answer.create_date)
        self.assertEqual(answer.expiry_date, start + relativedelta(years=1))
        self.assertEqual(answer.next_attempt_date, start + relativedelta(years=1))
        failed = self._run_evaluation(0)
        self.assertFalse(failed.expiry_date)
        self.assertEqual(
            failed.next_attempt_date,
            fields.Date.to_date(failed.create_date) + relativedelta(months=3),
        )

    def test_cooldown_blocks_new_attempt(self):
        """A failed attempt blocks retries until the cooldown elapses."""
        self._run_evaluation(0)
        with self.assertRaises(UserError):
            self.env["survey.user_input"].with_user(
                self.user
            )._start_certification_evaluation(self.cert_type)

    def test_start_evaluation_creates_answer(self):
        url = (
            self.env["survey.user_input"]
            .with_user(self.user)
            ._start_certification_evaluation(self.cert_type)
        )
        self.assertIn("/survey/start/%s" % self.survey.access_token, url)
        answer = self.env["survey.user_input"].search(
            [
                ("survey_id", "=", self.survey.id),
                ("company_id", "=", self.company.id),
                ("state", "=", "new"),
            ]
        )
        self.assertEqual(len(answer), 1)
        self.assertFalse(answer.test_entry)

    def test_positive_items(self):
        self.env["certification.positive.item"].create(
            {
                "survey_id": self.survey.id,
                "question_id": self.questions[0].id,
                "min_score": 2,
                "label": "First question OK",
                "icon": "fa-heart",
            }
        )
        self._run_evaluation(3)
        items = self.company._get_certification_positive_items(self.cert_type)
        # `description` is always present, and empty here: the microsite
        # template loops over these and over the vertical's curated
        # highlights with one body, so both sources hand it the same keys.
        self.assertEqual(
            items,
            [
                {
                    "label": "First question OK",
                    "description": None,
                    "icon": "fa-heart",
                }
            ],
        )
        # Below min_score the item disappears.
        self.company.certification_ids.user_input_id.user_input_line_ids.unlink()
        self.assertFalse(self.company._get_certification_positive_items(self.cert_type))

    def test_expiry_cron_drops_stale_status(self):
        self._run_evaluation(3)
        status = self.company.certification_ids
        status.expiry_date = fields.Date.today() - relativedelta(days=1)
        self.env["survey.user_input"]._cron_certification_expiry()
        self.assertFalse(self.company.certification_ids.exists())

    def test_menu_autocreated_per_type(self):
        """Every certification type gets its own gated menu tree."""
        self.assertTrue(self.cert_type.menu_id)
        self.assertTrue(self.cert_type.action_id)
        self.assertTrue(self.cert_type.start_action_id)
        self.assertEqual(self.cert_type.menu_id.group_ids, self.group_user)
        children = self.cert_type.menu_id.child_id
        self.assertEqual(len(children), 2)
        # Deleting the type cleans the generated records up.
        menu = self.cert_type.menu_id
        action = self.cert_type.action_id
        start_action = self.cert_type.start_action_id
        self.cert_type.unlink()
        self.assertFalse(menu.exists())
        self.assertFalse(action.exists())
        self.assertFalse(start_action.exists())

    def test_start_evaluation_denied_for_non_group_user(self):
        """A user outside the vertical's group cannot start an evaluation.

        Regression for the sudo-create escalation: any authenticated user
        could reach action_start_certification (RPC) or the controller and
        silently create a real evaluation for a vertical they do not belong
        to. Both entry points now go through the group check.
        """
        with self.assertRaises(UserError):
            self.env["survey.user_input"].with_user(
                self.plain_user
            ).action_start_certification(self.cert_type.id)
        with self.assertRaises(UserError):
            self.env["survey.user_input"].with_user(
                self.plain_user
            )._start_certification_evaluation(self.cert_type)
        # No evaluation leaked through despite the sudo create.
        self.assertFalse(
            self.env["survey.user_input"].search(
                [
                    ("survey_id", "=", self.survey.id),
                    ("partner_id", "=", self.plain_user.partner_id.id),
                ]
            )
        )

    def test_group_member_can_start_evaluation(self):
        """The positive counterpart: a vertical member is allowed through."""
        url = (
            self.env["survey.user_input"]
            .with_user(self.user)
            ._start_certification_evaluation(self.cert_type)
        )
        self.assertIn("/survey/start/", url)

    def test_no_scoring_survey_yields_no_level(self):
        """Switching the questionnaire to non-scoring recomputes the level."""
        answer = self._run_evaluation(3)
        self.assertEqual(answer.certification_level, "gold")
        # The scoring_type dependency must trigger a recompute to 'none'.
        self.survey.scoring_type = "no_scoring"
        self.assertEqual(answer.certification_level, "none")

    def test_certification_evaluation_count(self):
        """The company counter aggregates real evaluations in one query."""
        self.assertEqual(self.company.certification_evaluation_count, 0)
        self._run_evaluation(3)
        self._run_evaluation(0)
        self.company.invalidate_recordset(["certification_evaluation_count"])
        self.assertEqual(self.company.certification_evaluation_count, 2)
