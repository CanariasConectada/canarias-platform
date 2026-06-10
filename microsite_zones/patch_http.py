"""
Parche para odoo.http.Request._get_session_and_dbname

Problema: En modo multi-db (dbfilter = .*), cuando un usuario accede a la URL raíz (/)
sin tener una sesión previa, request.db es None porque _get_session_and_dbname solo
considera session.db, header X-Odoo-Database, o mono-db.

Como request.db es None, Odoo usa nodb_routing_map que SOLO incluye rutas con auth="none".
Esto hace que Home.index (web) capture / en lugar de Website.index (website),
redirigiendo a /odoo y luego a /web/login en lugar de mostrar la homepage.

Solución: Extender _get_session_and_dbname para que también considere el parámetro
de query string 'db', de forma similar a como ensure_db() lo hace para rutas auth="none".
"""

import logging
from odoo import http

_logger = logging.getLogger(__name__)

_original_get_session_and_dbname = http.Request._get_session_and_dbname


def _patched_get_session_and_dbname(self):
    """
    Versión parcheada que también busca 'db' en los query parameters
    de la petición HTTP cuando no hay sesión ni header X-Odoo-Database.
    """
    session, dbname = _original_get_session_and_dbname(self)

    if not dbname and self.httprequest:
        param_db = self.httprequest.args.get('db')
        if param_db:
            param_db = param_db.strip()
            # Validar contra db_filter para evitar db forging
            if param_db in http.db_filter([param_db]):
                dbname = param_db
                # Sincronizar con la sesión para que las siguientes peticiones
                # usen esta DB sin necesidad del parámetro en la URL
                if session.db != dbname:
                    session.db = dbname
                _logger.debug(
                    "[PATCH-HTTP] DB seleccionada desde query param: %s",
                    dbname,
                )
            else:
                _logger.warning(
                    "[PATCH-HTTP] Parámetro 'db' rechazado por db_filter: %s",
                    param_db,
                )

    return session, dbname


http.Request._get_session_and_dbname = _patched_get_session_and_dbname
_logger.info("[PATCH-HTTP] _get_session_and_dbname parcheado para soportar db en query params")
