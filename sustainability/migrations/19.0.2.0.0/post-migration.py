# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Reforma OCA 19.0.2.0.0.

* La puntuación manual pasa a ser durable: se persiste en el nuevo campo
  ``override_scoring_total`` (hasta ahora cualquier recomputación la perdía).
* Se corrigen las fronteras de los umbrales y se dejan de asignar niveles a
  encuestas que no son de certificación, así que se recomputan los campos
  almacenados.
* Se renombran los xmlids de vistas heredados de silver_economy por copy-paste
  (``*_inherit_silver`` dentro del módulo sustainability); las vistas antiguas
  se eliminan para que no queden herencias huérfanas aplicadas dos veces.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

RENAMED_VIEW_XMLIDS = [
    "sustainability.survey_button_retake_inherit_silver",
    "sustainability.survey_fill_form_done_inherit_silver",
    "sustainability.view_survey_user_input_tree_inherit_silver",
]


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})

    for xmlid in RENAMED_VIEW_XMLIDS:
        view = env.ref(xmlid, raise_if_not_found=False)
        if view:
            view.unlink()
            _logger.info("sustainability: vista huérfana %s eliminada.", xmlid)

    cr.execute(
        """
        UPDATE survey_user_input
        SET override_scoring_total = scoring_total
        WHERE is_manually_overridden
          AND (override_scoring_total IS NULL OR override_scoring_total = 0)
        """
    )
    _logger.info(
        "sustainability: override_scoring_total inicializado en %s registros.",
        cr.rowcount,
    )

    UserInput = env["survey.user_input"]
    inputs = UserInput.search([])
    for fname in ("certification_level", "next_attempt_date", "expiry_date"):
        env.add_to_compute(UserInput._fields[fname], inputs)

    Company = env["res.company"].with_context(active_test=False)
    companies = Company.search([])
    for fname in (
        "sustain_certification_level",
        "sustain_certification_date",
        "sustain_expiry_date",
        "sustain_cert_score",
    ):
        env.add_to_compute(Company._fields[fname], companies)
    _logger.info(
        "sustainability: recompute de certificación lanzado para %s evaluaciones "
        "y %s compañías.",
        len(inputs),
        len(companies),
    )
