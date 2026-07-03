# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Núcleo de certificación: umbrales, cooldown, override y sello de compañía.

Incluye además un test de convivencia con silver_economy: cada tipo de
encuesta debe puntuarse con los umbrales de SU módulo aunque ambos extiendan
survey.user_input con los mismos nombres de método.
"""
from dateutil.relativedelta import relativedelta

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSustainabilityCertification(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env["res.company"].create({"name": "Sustain Test Co"})
        cls.survey = cls.env["survey.survey"].create(
            {
                "title": "Sustainability Test Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
                "is_sustainability": True,
            }
        )

    def _make_input(self, score, survey=None, state="done"):
        user_input = self.env["survey.user_input"].create(
            {
                "survey_id": (survey or self.survey).id,
                "company_id": self.company.id,
                "test_entry": False,
            }
        )
        user_input.state = state
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

    def test_company_badge_lifecycle(self):
        """El sello de la compañía sigue a la última evaluación válida."""
        self.assertEqual(self.company.sustain_certification_level, "none")
        user_input = self._make_input(60)
        self.assertEqual(self.company.sustain_certification_level, "silver")
        self.assertEqual(
            self.company.sustain_expiry_date,
            user_input.create_date.date() + relativedelta(years=1),
        )
        user_input.unlink()
        self.assertEqual(self.company.sustain_certification_level, "none")

    def test_cooldown_after_failure(self):
        """Tras suspender, la misma empresa no puede reintentar hasta la fecha."""
        failed = self._make_input(10)
        expected = failed.create_date.date() + relativedelta(months=3)
        self.assertEqual(failed.next_attempt_date, expected)
        self.assertEqual(
            self.env["survey.user_input"]._get_certification_cooldown_date(
                self.survey, self.company
            ),
            expected,
        )

    def test_override_uses_sustainability_manager_group(self):
        """El override valida contra el grupo manager de ESTE módulo."""
        manager = self.env["res.users"].create(
            {
                "name": "Sustain Manager",
                "login": "sustain_manager_test",
                "company_id": self.company.id,
                "company_ids": [(4, self.company.id)],
                "group_ids": [
                    (4, self.env.ref("base.group_user").id),
                    (4, self.env.ref("sustainability.group_sustainability_manager").id),
                ],
            }
        )
        user_input = self._make_input(45)
        user_input.with_user(manager).action_override_score(72, reason="ajuste")
        self.assertEqual(user_input.scoring_total, 72)
        self.assertEqual(user_input.certification_level, "gold")
        # Recomputar no descarta el override.
        user_input._compute_scoring_values()
        self.assertEqual(user_input.scoring_total, 72)

    def test_cross_module_thresholds(self):
        """Con silver_economy instalado, cada encuesta usa SUS umbrales."""
        if "is_silver_economy" not in self.env["survey.survey"]._fields:
            self.skipTest("silver_economy no instalado")
        self.survey.sustain_gold_min = 50
        silver_survey = self.env["survey.survey"].create(
            {
                "title": "Silver Cross Survey",
                "survey_type": "survey",
                "scoring_type": "scoring_without_answers",
                "is_silver_economy": True,
                "silver_gold_min": 75,
            }
        )
        sust_input = self._make_input(60)
        silver_input = self._make_input(60, survey=silver_survey)
        # 60 >= 50 → oro con los umbrales de sostenibilidad...
        self.assertEqual(sust_input.certification_level, "gold")
        # ...pero solo plata con los de silver_economy (oro exige 75).
        self.assertEqual(silver_input.certification_level, "silver")
        config = silver_survey._get_certification_config()
        self.assertEqual(config["manager_group"], "silver_economy.group_silver_manager")
        # Y la encuesta de cada tipo es "certification survey" para ambos.
        self.assertTrue(self.survey.is_certification_survey)
        self.assertTrue(silver_survey.is_certification_survey)
