# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Reforma OCA 19.0.2.0.0.

* La puntuación manual pasa a ser durable: se persiste en el nuevo campo
  ``override_scoring_total`` (hasta ahora cualquier recomputación la perdía).
  Para los registros ya marcados como editados, el mejor valor disponible es
  el ``scoring_total`` actual.
* La lógica de umbrales corrige las fronteras (una puntuación igual al mínimo
  de un nivel ahora otorga ese nivel) y deja de asignar niveles a encuestas
  que no son de certificación, así que se recomputan los campos almacenados.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    cr.execute(
        """
        UPDATE survey_user_input
        SET override_scoring_total = scoring_total
        WHERE is_manually_overridden
          AND (override_scoring_total IS NULL OR override_scoring_total = 0)
        """
    )
    _logger.info(
        "silver_economy: override_scoring_total inicializado en %s registros.",
        cr.rowcount,
    )

    UserInput = env["survey.user_input"]
    inputs = UserInput.search([])
    for fname in ("certification_level", "next_attempt_date", "expiry_date"):
        env.add_to_compute(UserInput._fields[fname], inputs)

    Company = env["res.company"].with_context(active_test=False)
    companies = Company.search([])
    for fname in (
        "silver_certification_level",
        "silver_certification_date",
        "silver_expiry_date",
        "silver_cert_score",
    ):
        env.add_to_compute(Company._fields[fname], companies)
    _logger.info(
        "silver_economy: recompute de certificación lanzado para %s evaluaciones "
        "y %s compañías.",
        len(inputs),
        len(companies),
    )
