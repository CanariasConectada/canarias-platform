# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestEvaluationStart(CertificationCase):
    """Starting an evaluation has to say WHICH seal.

    Reported on 2026-08-16: "veo que agrupaste las certificaciones, pero no
    veo que permitas el tema de que la empresa pueda crear un silver economy
    o un sostenibilidad".

    Merging the two per-seal menus into one list took the two "Nueva
    Evaluación" entries with them. Nothing was broken in the engine -- the
    engine had simply lost every door into it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A second seal whose group nobody in the fixtures holds, so "only
        # what you may sit" has something to leave out.
        cls.locked_group = cls.env["res.groups"].create(
            {
                "name": "Test Locked Seal User",
                "implied_ids": [
                    (
                        4,
                        cls.env.ref(
                            "company_certification.group_certification_user"
                        ).id,
                    )
                ],
            }
        )
        cls.locked_survey = cls.env["survey.survey"].create(
            {
                "title": "Test Locked Seal Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
                "access_mode": "public",
                "users_login_required": True,
            }
        )
        cls.locked_type = cls.env["certification.type"].create(
            {
                "name": "Test Locked Seal",
                "code": "test_locked_seal",
                "survey_id": cls.locked_survey.id,
                "group_user_id": cls.locked_group.id,
            }
        )

    def _wizard(self, user=None, cert_type=None):
        """The wizard as the dialog leaves it: a seal already picked.

        ``certification_type_id`` is required, so the transient row cannot be
        written without one. In the interface that is never a problem -- the
        record is only written when Start is pressed -- but a test has to say
        what the merchant clicked.
        """
        return (
            self.env["certification.evaluation.start"]
            .with_user(user or self.user)
            .create({"certification_type_id": (cert_type or self.cert_type).id})
        )

    def test_the_door_back_into_the_engine_exists(self):
        """The regression itself, guarded where it happened.

        Consolidating the lists is a good idea that has now cost the platform
        its "New Evaluation" entry once. If it is ever tidied away again this
        is the test that says so.
        """
        menu = self.env.ref(
            "company_certification.menu_certification_evaluation_start",
            raise_if_not_found=False,
        )
        self.assertTrue(menu, "there has to be a way to start an evaluation")
        self.assertTrue(menu.active)
        self.assertEqual(
            menu.parent_id,
            self.env.ref("company_certification.menu_certification_root"),
            "it belongs beside the list it fills, not in a menu of its own",
        )

    def test_the_picker_offers_the_seals_this_account_may_sit(self):
        wizard = self._wizard()
        self.assertIn(self.cert_type, wizard.available_type_ids)
        self.assertNotIn(
            self.locked_type,
            wizard.available_type_ids,
            "offering a seal only to refuse it after the click is worse than "
            "not offering it",
        )

    def test_picking_a_seal_opens_its_questionnaire(self):
        wizard = self._wizard(cert_type=self.cert_type)
        self.assertFalse(wizard.blocker)

        action = wizard.action_start()

        self.assertEqual(action["type"], "ir.actions.act_url")
        self.assertIn(self.survey.access_token, action["url"])
        started = self.env["survey.user_input"].search(
            [("survey_id", "=", self.survey.id), ("company_id", "=", self.company.id)]
        )
        self.assertTrue(started, "the evaluation has to actually exist afterwards")
        self.assertEqual(started.certification_type_id, self.cert_type)

    def test_a_cooldown_is_announced_before_the_click_not_after(self):
        """A red error box after pressing Start reads like a platform failure.

        The same sentence inside the still-open dialog reads like an answer.
        """
        self._run_evaluation(0)

        wizard = self._wizard(cert_type=self.cert_type)

        self.assertTrue(wizard.blocker, "the cooldown has to be visible in the dialog")
        with self.assertRaises(UserError):
            wizard.action_start()

    def test_a_seal_with_no_questionnaire_says_so(self):
        self.cert_type.survey_id.active = False
        wizard = self._wizard(cert_type=self.cert_type)
        self.assertTrue(wizard.blocker)

    def test_the_picker_never_decides_who_may_sit_what(self):
        """Reaching past the picker still hits the engine's own gate.

        The wizard filters the list for convenience. If that were also the
        authorisation, anyone able to write an id into the field would hold
        every seal on the platform.
        """
        wizard = self._wizard(cert_type=self.locked_type)
        with self.assertRaises(UserError):
            wizard.action_start()
