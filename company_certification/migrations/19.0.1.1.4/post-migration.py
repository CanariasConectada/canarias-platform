# Copyright 2026 Canarias Conectada
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
"""Repara los sellos cuya fecha se calculó con el ``@api.depends`` incompleto.

Hasta 19.0.1.1.4, ``survey.user_input.expiry_date`` y ``next_attempt_date`` no
dependían de los campos de plazos de ``certification.type``, así que cada
edición de ``validity_years`` / ``cooldown_months`` dejaba congeladas las
evaluaciones ya hechas en la fecha ANTIGUA — y ``res.company.certification``
guarda una copia de esa fecha, que es justo la que leen la chapa pública
(``_is_valid()``) y el cron de caducidad.

Arreglar el ``@api.depends`` sólo arregla lo que se recalcule a partir de
ahora: el ORM no tiene motivo para recalcular un campo almacenado cuyas
dependencias no han cambiado. Por eso las filas que ya están en la base de
datos hay que recalcularlas una vez aquí, y refrescar desde ellas la copia de
cada compañía.
"""
import logging

from odoo import SUPERUSER_ID, api

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    model = env["survey.user_input"]
    evaluations = model.search(
        [
            ("certification_type_id", "!=", False),
            ("state", "=", "done"),
            ("test_entry", "=", False),
            ("company_id", "!=", False),
        ]
    )
    if not evaluations:
        _logger.info("company_certification: no hay evaluaciones que recalcular.")
        return

    fnames = ("expiry_date", "next_attempt_date")
    for fname in fnames:
        env.add_to_compute(model._fields[fname], evaluations)
    evaluations.flush_recordset(fnames)

    # Las filas de res.company.certification son una COPIA de expiry_date, y
    # esa copia sólo se refresca desde survey.user_input.write(); un recálculo
    # se vuelca con _write_multi() y nunca pasa por write(). Hay que empujarla.
    evaluations._refresh_company_certification()
    _logger.info(
        "company_certification: recalculadas %s evaluaciones y refrescados "
        "los sellos de compañía derivados de ellas.",
        len(evaluations),
    )
