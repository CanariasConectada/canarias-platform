# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Editar los plazos de una vertical no puede dejar sellos caducados de más.

Los dos cómputos almacenados (``expiry_date`` y ``next_attempt_date``) leían
``validity_years`` / ``cooldown_months`` del tipo de certificación sin
declararlos en su ``@api.depends``. Un administrador ampliaba la vigencia de 1
a 2 años y NADA se recalculaba: el cron seguía caducando y avisando por la
fecha vieja, revocando en silencio sellos válidos.

Y con el ``depends`` arreglado tampoco bastaba: ``res.company.certification``
guarda una COPIA de la fecha (la que leen la chapa pública y el cron), y esa
copia sólo se refresca desde ``survey.user_input.write()`` — un recálculo se
vuelca con ``_write_multi()`` y nunca pasa por ``write()``. De ahí que estos
tests comprueben SIEMPRE los dos lados: la evaluación y la copia de compañía.
"""
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import tagged

from .common import CertificationCase


@tagged("post_install", "-at_install")
class TestCertificationTypeTiming(CertificationCase):
    def _company_status(self):
        """Lee la fila de estado de la base, no de la caché del one2many.

        ``_refresh()`` puede borrar y volver a crear el registro, con lo que un
        recordset cacheado apuntaría a un id que ya no existe.
        """
        return self.env["res.company.certification"].search(
            [
                ("company_id", "=", self.company.id),
                ("type_id", "=", self.cert_type.id),
            ]
        )

    def test_validity_extension_propagates_to_evaluation_and_company(self):
        """Ampliar la vigencia mueve la caducidad en la evaluación Y en la copia."""
        answer = self._run_evaluation(3)
        start = fields.Date.to_date(answer.create_date)
        self.assertEqual(answer.expiry_date, start + relativedelta(years=1))
        self.assertEqual(
            self._company_status().expiry_date, start + relativedelta(years=1)
        )

        self.cert_type.validity_years = 2

        self.assertEqual(
            answer.expiry_date,
            start + relativedelta(years=2),
            "la evaluación debe recalcular su caducidad al cambiar el plazo",
        )
        self.assertEqual(
            self._company_status().expiry_date,
            start + relativedelta(years=2),
            "la copia de la compañía es la que leen la chapa pública y el cron",
        )

    def test_validity_extension_moves_next_attempt_of_awarded_seal(self):
        """Con sello, el siguiente intento va por vigencia, no por cooldown."""
        answer = self._run_evaluation(3)
        start = fields.Date.to_date(answer.create_date)
        self.assertEqual(answer.next_attempt_date, start + relativedelta(years=1))

        self.cert_type.validity_years = 3

        self.assertEqual(answer.next_attempt_date, start + relativedelta(years=3))

    def test_cooldown_change_propagates_to_next_attempt_date(self):
        """Cambiar el cooldown reabre (o retrasa) el reintento de un suspenso."""
        failed = self._run_evaluation(0)
        start = fields.Date.to_date(failed.create_date)
        self.assertEqual(failed.next_attempt_date, start + relativedelta(months=3))

        self.cert_type.cooldown_months = 6

        self.assertEqual(failed.next_attempt_date, start + relativedelta(months=6))
        # Un suspenso no genera sello, así que no hay copia que tocar.
        self.assertFalse(self._company_status())

    def test_expiry_cron_keeps_extended_certification(self):
        """El cron no puede caducar un sello cuya vigencia se acaba de ampliar.

        Reproduce el daño real: la copia de la compañía se quedó con la fecha
        vieja (aquí, ya vencida) y el cron la habría borrado — y avisado al
        responsable de la encuesta — pese a que la vertical ahora da 2 años.
        """
        answer = self._run_evaluation(3)
        status = self._company_status()
        status.expiry_date = fields.Date.today() - relativedelta(days=1)

        self.cert_type.validity_years = 2
        self.env["survey.user_input"]._cron_certification_expiry()

        status = self._company_status()
        self.assertTrue(status, "el sello ampliado debe sobrevivir al cron")
        self.assertEqual(
            status.expiry_date,
            fields.Date.to_date(answer.create_date) + relativedelta(years=2),
        )
        self.assertTrue(status._is_valid())

    def test_unrelated_type_edit_leaves_the_seal_alone(self):
        """Editar algo que no son plazos no tiene por qué tocar los sellos."""
        answer = self._run_evaluation(3)
        expiry = self._company_status().expiry_date

        self.cert_type.website_title = "Otro título"

        self.assertEqual(answer.expiry_date, expiry)
        self.assertEqual(self._company_status().expiry_date, expiry)
