# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Guardas de la unificación: un cuestionario, un dueño.

Antes de este cambio había dos cuestionarios de Sostenibilidad idénticos al
byte, uno en ``company_certification`` y otro aquí, y la marca
``is_sustainability`` estaba en el de aquí. Resultado: un comercio que
rellenaba el del otro módulo puntuaba allí y aquí no existía. Estos tests son
lo que impide que vuelva.
"""

from unittest.mock import patch

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

    # ------------------------------------------------------------------
    # La marca se cura sola
    # ------------------------------------------------------------------
    # Los tests de arriba comprueban que la marca está bien puesta. Estos
    # comprueban que VUELVE a estarlo si se pierde, que es otra cosa.
    #
    # Se verificó en una copia desechable de la base real: borrar la marca por
    # SQL y lanzar `odoo -u sustainability` NO la devuelve. El
    # <data noupdate="1"> se salta en toda actualización y la migración a
    # 19.0.1.5.0 ya corrió. Y perderla no levanta un error en ninguna parte:
    # las ir.rule dejan de casar con nada y las páginas públicas se pintan
    # vacías. Un fallo mudo es el peor tipo de fallo.

    def _flagged_surveys(self):
        return (
            self.env["survey.survey"]
            .with_context(active_test=False)
            .search([("is_sustainability", "=", True)])
        )

    def test_ensure_restores_the_flag_when_it_was_lost(self):
        """La regresión por la que existe todo este arreglo.

        Sin marca, la vertical entera se queda muda sin decir nada.
        """
        owner = self.env.ref("company_certification.survey_sustainability")
        owner.is_sustainability = False
        self.assertFalse(
            self._flagged_surveys(), "el montaje del test debe dejar cero marcados"
        )

        restored = self.env["survey.survey"]._ensure_sustainability_flag()

        self.assertEqual(restored, owner)
        self.assertTrue(
            owner.is_sustainability,
            "tras llamar al método de reparación el dueño debe volver a "
            "llevar la marca",
        )
        self.assertEqual(self._flagged_surveys(), owner)

    def test_ensure_clears_the_flag_from_a_rogue_survey(self):
        """Dos marcados es peor que ninguno: el resultado depende del orden.

        Es el fallo original de este módulo, y puede volver con un duplicado
        creado a mano desde la interfaz.
        """
        owner = self.env.ref("company_certification.survey_sustainability")
        rogue = self.env["survey.survey"].create(
            {"title": "Copia intrusa Sostenibilidad", "is_sustainability": True}
        )

        self.env["survey.survey"]._ensure_sustainability_flag()

        self.assertFalse(
            rogue.is_sustainability,
            "al cuestionario intruso hay que quitarle la marca",
        )
        self.assertTrue(owner.is_sustainability, "y el dueño debe conservarla")
        self.assertEqual(self._flagged_surveys(), owner)

    def test_ensure_is_idempotent_and_writes_nothing_when_state_is_correct(self):
        """Se llama en cada carga del registro, o sea en cada arranque.

        Si escribiera siempre, cada arranque pagaría una escritura y un
        registro en el historial del cuestionario a cambio de nada.
        """
        survey_model = self.env["survey.survey"]
        survey_model._ensure_sustainability_flag()
        survey_class = type(survey_model)

        with patch.object(
            survey_class, "write", autospec=True, side_effect=survey_class.write
        ) as write_mock:
            survey_model._ensure_sustainability_flag()

        self.assertFalse(
            write_mock.called,
            "con el estado ya correcto la segunda llamada no debe escribir "
            f"nada, y escribió {write_mock.call_args_list}",
        )
        self.assertEqual(len(self._flagged_surveys()), 1)

    def test_ensure_does_not_raise_when_the_owner_cannot_be_resolved(self):
        """Se la llama desde _register_hook: si lanza, el registro no carga.

        O sea que un xmlid perdido dejaría el servicio caído en vez de una
        vertical coja. Aquí se rompen las dos vías de resolución -el xmlid del
        cuestionario y el survey_id del tipo de certificación- y se exige que
        el método se queje en el log y deje el estado como estaba.
        """
        owner = self.env.ref("company_certification.survey_sustainability")
        cert_type = self.env.ref(
            "company_certification.certification_type_sustainability"
        )
        cert_type.survey_id = False
        self.env["ir.model.data"].search(
            [
                ("module", "=", "company_certification"),
                ("name", "=", "survey_sustainability"),
            ]
        ).unlink()

        with self.assertLogs(
            "odoo.addons.sustainability.models.survey_survey", level="ERROR"
        ):
            resolved = self.env["survey.survey"]._ensure_sustainability_flag()

        self.assertFalse(
            resolved, "sin dueño resoluble el método debe devolver vacío, no adivinar"
        )
        self.assertEqual(
            self._flagged_surveys(),
            owner,
            "el estado debe quedarse como estaba: reparar a ciegas sería peor",
        )
