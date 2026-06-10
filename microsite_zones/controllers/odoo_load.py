# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
from odoo import http
from odoo.http import request
from odoo.addons.web.controllers.home import Home
from .login_debug import debug_logger

_logger = logging.getLogger(__name__)


class OdooLoadController(Home):
    """
    Controlador que intercepta la carga de /odoo para establecer la compañía activa
    basándose en el parámetro cids de la URL.
    
    SOLUCIÓN C: Modificar el contexto del usuario directamente en el servidor
    al cargar /odoo con parámetro cids.
    """

    @http.route(['/odoo', '/odoo/<path:subpath>'], type='http', auth='none', website=False, readonly=False)
    def web_client(self, s_action=None, subpath=None, **kwargs):
        """
        Sobrescribe la carga de /odoo para procesar el parámetro cids.
        Si viene cids en la URL, establece la cookie y el contexto de compañía.
        """
        _logger.warning("[ODOO-LOAD-DEBUG] uid=%s sid=%s cookie=%s", request.session.uid, (request.session.sid or "")[:12], (request.httprequest.headers.get("Cookie","NONE"))[:150])
        cids = kwargs.get('cids') or request.params.get('cids')
        
        if cids and request.session.uid:
            debug_logger.info("[ODOO-LOAD] Detectado parámetro cids con usuario autenticado", 
                             cids=cids, 
                             user_id=request.session.uid)
            
            try:
                # Parsear los IDs de compañía
                company_ids = [int(cid) for cid in str(cids).split(',')]
                primary_company_id = company_ids[0]
                
                # Obtener el usuario desde la sesión
                user = request.env['res.users'].sudo().browse(request.session.uid)
                user_company_ids = user.company_ids.ids
                
                debug_logger.info("[ODOO-LOAD] Verificando permisos",
                                 primary_company_id=primary_company_id,
                                 user_company_ids=user_company_ids,
                                 user_name=user.name)
                
                # Verificar que el usuario tiene acceso a la compañía
                if primary_company_id in user_company_ids:
                    # Establecer el contexto de compañía para esta petición
                    allowed_company_ids = [cid for cid in company_ids if cid in user_company_ids]
                    
                    debug_logger.info("[ODOO-LOAD] Estableciendo compañías permitidas",
                                     allowed_company_ids=allowed_company_ids)
                    
                    # Guardar en la sesión para futuras peticiones
                    request.session['cids'] = allowed_company_ids
                    
                    debug_logger.info("[ODOO-LOAD] Contexto actualizado correctamente")
                else:
                    debug_logger.warning("[ODOO-LOAD] Usuario no tiene acceso a la compañía",
                                        primary_company_id=primary_company_id)
            except Exception as e:
                debug_logger.error("[ODOO-LOAD] Error procesando cids", error=str(e))
        
        # Llamar al método padre con los parámetros correctos
        if subpath:
            return super().web_client(s_action=s_action, subpath=subpath, **kwargs)
        return super().web_client(s_action=s_action, **kwargs)
