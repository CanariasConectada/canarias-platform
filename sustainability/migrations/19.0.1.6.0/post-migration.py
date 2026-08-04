# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Repara la marca ``is_sustainability`` en bases donde ya estaba mal.

A partir de esta versión la marca se cura sola en cada carga del registro
(``SurveySurvey._register_hook``), así que esta migración no es la que
mantiene el invariante: es la que arregla la base ANTES de que nadie la
mire, en el mismo ``-u`` que trae el arreglo, sin esperar al hook.

Merece la pena porque hasta aquí la marca sólo se ponía en el ``-i``
(``<data noupdate="1">``, que Odoo se salta en todo ``-u``) y en la
migración a 19.0.1.5.0, que corre una única vez. Cualquier base que la
perdiera por el camino se quedaba con la vertical muda y sin un solo error
en los logs.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    owner = env["survey.survey"]._ensure_sustainability_flag()
    if not owner:
        # El método ya ha dejado el motivo en el log; aquí sólo se deja claro
        # que el `-u` termina sin garantizar el invariante.
        _logger.error(
            "sustainability 19.0.1.6.0: la actualización termina sin poder "
            "asegurar la marca is_sustainability."
        )
