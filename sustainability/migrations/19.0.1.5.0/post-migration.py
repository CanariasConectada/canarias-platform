# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Jubila la copia del cuestionario de Sostenibilidad que traía este módulo.

El cuestionario pasa a tener un solo dueño, ``company_certification``, y la
marca ``is_sustainability`` se pone ahora sobre el suyo. La copia que publicaba
este módulo queda sin función.

Qué hace exactamente, y en este orden:

1. Le quita la marca a la copia. Esto es lo que de verdad importa: mientras la
   lleve, las búsquedas de este módulo devolverían DOS cuestionarios y el nivel
   de un comercio dependería de cuál saliera primero.
2. La borra SOLO si no tiene ninguna respuesta.

Si tiene respuestas se queda donde está, desmarcada y archivada, y se deja
constancia en el log. Borrar evaluaciones que un comerciante rellenó de verdad
no es tarea de una migración: en el Doodba las cuatro copias tienen cero
respuestas, pero el sistema antiguo llega a este punto con 1 en la suya, y esta
migración tiene que ser segura también allí.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)

OLD_SURVEY = "sustainability.sust_economy_master_survey"
NEW_SURVEY = "company_certification.survey_sustainability"


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})

    new_survey = env.ref(NEW_SURVEY, raise_if_not_found=False)
    if not new_survey:
        # Sin el cuestionario del dueño no hay nada a lo que migrar; dejar la
        # copia intacta es mucho mejor que quedarse sin ninguno.
        _logger.error(
            "%s no existe: se deja la copia de sustainability tal cual", NEW_SURVEY
        )
        return
    new_survey.is_sustainability = True

    old_survey = env.ref(OLD_SURVEY, raise_if_not_found=False)
    if not old_survey:
        return

    old_survey.is_sustainability = False

    answers = env["survey.user_input"].search_count([("survey_id", "=", old_survey.id)])
    if answers:
        old_survey.active = False
        _logger.warning(
            "El cuestionario de Sostenibilidad duplicado (id=%s) conserva %s "
            "respuestas: se desmarca y se archiva, pero NO se borra. Revisar a "
            "mano si esas evaluaciones deben pasarse al cuestionario %s.",
            old_survey.id,
            answers,
            new_survey.id,
        )
        return

    _logger.info(
        "Borrando el cuestionario de Sostenibilidad duplicado (id=%s, sin "
        "respuestas); el dueño pasa a ser %s",
        old_survey.id,
        new_survey.id,
    )
    old_survey.unlink()
