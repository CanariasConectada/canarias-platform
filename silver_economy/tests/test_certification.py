# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Núcleo de certificación: umbrales, cooldown, override y sello de compañía."""
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSilverCertification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Silver Test Co"})
        cls.survey = cls.env["survey.survey"].create(
            {
                "title": "Silver Test Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
                "is_silver_economy": True,
            }
        )

    def _make_input(self, score, state="done"):
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": self.survey.id,
                "company_id": self.company.id,
                "test_entry": False,
            }
        )
        user_input.state = state
        # scoring_total es un compute almacenado sin inverse: la escritura
        # directa fija el valor y dispara los dependientes (certificación).
        user_input.scoring_total = score
        return user_input

    def test_threshold_boundaries(self):
        """El mínimo de cada nivel otorga ese nivel (fronteras inclusivas)."""
        cases = [
            (0, "none"),
            (39.9, "none"),
            (40, "bronze"),
            (55.9, "bronze"),
            (56, "silver"),
            (70.9, "silver"),
            (71, "gold"),
            (80, "gold"),
        ]
        for score, expected in cases:
            user_input = self._make_input(score)
            self.assertEqual(
                user_input.certification_level,
                expected,
                "score %s debe dar %s" % (score, expected),
            )

    def test_non_certification_survey_gets_no_level(self):
        """Una encuesta puntuada normal no reparte sellos."""
        plain = self.env["survey.survey"].create(
            {
                "title": "Plain Scored Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
            }
        )
        user_input = self.env["survey.user_input"].create(
            {"survey_id": plain.id, "company_id": self.company.id}
        )
        user_input.scoring_total = 75
        self.assertEqual(user_input.certification_level, "none")

    def test_company_badge_lifecycle(self):
        """El sello de la compañía sigue a la última evaluación válida."""
        self.assertEqual(self.company.silver_certification_level, "none")
        user_input = self._make_input(60)
        self.assertEqual(user_input.certification_level, "silver")
        self.assertEqual(self.company.silver_certification_level, "silver")
        self.assertEqual(
            self.company.silver_expiry_date,
            user_input.create_date.date() + relativedelta(years=1),
        )
        user_input.unlink()
        self.assertEqual(self.company.silver_certification_level, "none")
        self.assertFalse(self.company.silver_expiry_date)

    def test_cooldown_after_failure(self):
        """Tras suspender, la misma empresa no puede reintentar hasta la fecha."""
        failed = self._make_input(10)
        self.assertEqual(failed.certification_level, "none")
        expected = failed.create_date.date() + relativedelta(months=3)
        self.assertEqual(failed.next_attempt_date, expected)
        UserInput = self.env["survey.user_input"]
        self.assertEqual(
            UserInput._get_certification_cooldown_date(self.survey, self.company),
            expected,
        )
        user = self.env["res.users"].create(
            {
                "name": "Silver Employee",
                "login": "silver_employee",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
                "group_ids": [
                    (4, self.env.ref("base.group_user").id),
                    (4, self.env.ref("silver_economy.group_silver_user").id),
                ],
            }
        )
        with self.assertRaises(UserError):
            UserInput.with_user(user)._create_certification_answer(self.survey)

    def test_override_score_is_durable(self):
        """El override manual sobrevive a la recomputación del scoring."""
        manager = self.env["res.users"].create(
            {
                "name": "Silver Manager",
                "login": "silver_manager_test",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
                "group_ids": [
                    (4, self.env.ref("base.group_user").id),
                    (4, self.env.ref("silver_economy.group_silver_manager").id),
                ],
            }
        )
        user_input = self._make_input(45)
        self.assertEqual(user_input.certification_level, "bronze")
        user_input.with_user(manager).action_override_score(72, reason="ajuste")
        self.assertTrue(user_input.is_manually_overridden)
        self.assertEqual(user_input.scoring_total, 72)
        self.assertEqual(user_input.certification_level, "gold")
        self.assertEqual(user_input.original_scoring_total, 45)
        # Una recomputación externa no debe descartar el override.
        user_input._compute_scoring_values()
        self.assertEqual(user_input.scoring_total, 72)
        user_input.with_user(manager).action_reset_override()
        self.assertFalse(user_input.is_manually_overridden)
        # Sin líneas de respuesta el scoring vuelve al valor computado (0).
        self.assertEqual(user_input.scoring_total, 0)

    def test_override_requires_manager(self):
        user = self.env["res.users"].create(
            {
                "name": "Silver Plain User",
                "login": "silver_plain_user",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
                "group_ids": [
                    (4, self.env.ref("base.group_user").id),
                    (4, self.env.ref("silver_economy.group_silver_user").id),
                ],
            }
        )
        user_input = self._make_input(45)
        with self.assertRaises(UserError):
            user_input.with_user(user).action_override_score(80)

    def test_certification_config_uses_own_thresholds(self):
        """El hook cooperativo devuelve los umbrales del módulo correcto."""
        self.survey.silver_gold_min = 60
        config = self.survey._get_certification_config()
        self.assertEqual(config["gold_min"], 60)
        self.assertEqual(config["manager_group"], "silver_economy.group_silver_manager")
        user_input = self._make_input(60)
        self.assertEqual(user_input.certification_level, "gold")

    def test_expiry_alert_cron_window(self):
        """La alerta de expiración solo abarca los sellos vencidos ayer."""
        user_input = self._make_input(60)
        self.assertTrue(user_input.expiry_date)
        domain = user_input._silver_evaluation_domain() + [
            ("certification_level", "!=", "none"),
            ("expiry_date", "=", fields.Date.today() - relativedelta(days=1)),
        ]
        self.assertNotIn(user_input, self.env["survey.user_input"].search(domain))
