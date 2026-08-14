# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Ganchos de instalación de silver_economy."""


def post_init_hook(env):
    """Deja la marca ``is_silver_economy`` puesta al terminar un ``-i``.

    El fichero ``data/silver_economy_survey.xml`` también la pone, pero es un
    ``<data noupdate="1">``: sólo se aplica cuando el registro no existía, o
    sea nunca en un ``-u``. Este gancho cubre la instalación limpia sin
    depender de ese detalle, y el resto de la vida del módulo lo cubre
    ``SurveySurvey._register_hook``.
    """
    env["survey.survey"]._ensure_silver_economy_flag()
