# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Guardas de la unificación: un cuestionario, un dueño.

Antes de este cambio había dos cuestionarios de Sostenibilidad idénticos al
byte, uno en ``company_certification`` y otro aquí, y la marca
``is_sustainability`` estaba en el de aquí. Resultado: un comercio que
rellenaba el del otro módulo puntuaba allí y aquí no existía. Estos tests son
lo que impide que vuelva.
"""

from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestSingleSurveyOwner(TransactionCase):
    def test_exactly_one_survey_carries_the_sustainability_flag(self):
        """Con dos marcados, el nivel de un comercio depende de cuál salga primero.

        Es el fallo más difícil de ver de todos: no rompe nada, sólo devuelve
        a veces una respuesta y a veces otra.
        """
        flagged = (
            self.env["survey.survey"]
            .with_context(active_test=False)
            .search([("is_sustainability", "=", True)])
        )
        self.assertEqual(
            len(flagged),
            1,
            "debe haber exactamente un cuestionario de Sostenibilidad marcado, "
            f"y hay {len(flagged)}: {flagged.mapped('title')}",
        )

    def test_the_flagged_survey_is_the_one_company_certification_owns(self):
        owner_survey = self.env.ref("company_certification.survey_sustainability")
        flagged = (
            self.env["survey.survey"]
            .with_context(active_test=False)
            .search([("is_sustainability", "=", True)])
        )
        self.assertEqual(flagged, owner_survey)

    def test_this_module_no_longer_publishes_a_survey(self):
        """Si alguien vuelve a añadir aquí un survey.survey, esto lo caza."""
        own = self.env["ir.model.data"].search(
            [("module", "=", "sustainability"), ("model", "=", "survey.survey")]
        )
        self.assertFalse(
            own,
            "sustainability no debe publicar cuestionarios: el dueño es "
            f"company_certification. Encontrados: {own.mapped('name')}",
        )

    def test_the_certification_type_points_at_the_same_survey(self):
        """Las dos vías -tipo de certificación y marca- deben coincidir.

        Si divergen, un comercio sale certificado por una y no por la otra,
        que es exactamente el síntoma que motivó este cambio.
        """
        cert_type = self.env.ref(
            "company_certification.certification_type_sustainability",
            raise_if_not_found=False,
        )
        if not cert_type:
            self.skipTest("company_certification no define el tipo sustainability")
        flagged = (
            self.env["survey.survey"]
            .with_context(active_test=False)
            .search([("is_sustainability", "=", True)])
        )
        self.assertEqual(
            cert_type.survey_id,
            flagged,
            "el tipo de certificación y la marca apuntan a cuestionarios distintos",
        )
