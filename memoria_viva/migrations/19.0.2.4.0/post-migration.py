# -*- coding: utf-8 -*-
"""Preserva el comportamiento de producción al introducir el toggle
``memoria_viva_enabled`` (website-specific).

Antes la página /memoria-viva estaba hardcodeada al website de Guanarteme. Ahora
la disponibilidad la gobierna el campo ``memoria_viva_enabled`` (default False).
Para no romper producción, aquí marcamos como habilitado el/los website(s) cuyo
dominio contenga 'guanarteme.canariasconectada.es'.
"""
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return

    # Guarda defensiva: la columna debe existir (la crea el ORM al actualizar
    # el módulo antes de las post-migraciones, pero comprobamos por seguridad).
    cr.execute(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'website' "
        "AND column_name = 'memoria_viva_enabled'"
    )
    if not cr.fetchone():
        _logger.info(
            "memoria_viva: columna memoria_viva_enabled no existe, nada que hacer.")
        return

    # Patrón ESTRICTO: el '//' delante del host evita falsos positivos como
    # 'fisioterapiaguanarteme.canariasconectada.es' (contiene la subcadena
    # 'guanarteme.canariasconectada.es' pero NO es el microsite de Guanarteme).
    cr.execute(
        "UPDATE website SET memoria_viva_enabled = TRUE "
        "WHERE domain ILIKE %s",
        ('%//guanarteme.canariasconectada.es',),
    )
    _logger.info(
        "memoria_viva: %s website(s) Guanarteme marcados con "
        "memoria_viva_enabled=TRUE.", cr.rowcount,
    )
