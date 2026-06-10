# -*- coding: utf-8 -*-
"""
Microsite Company Switch - Controllers principales

Funcionalidades:
- Endpoint de debug para verificar estado
"""
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)


class MicrositeCompanySwitchController(http.Controller):
    """
    Controller principal para debug y utilidades.
    El cambio de compañía se maneja ahora en models/ir_http.py
    """
    
    @http.route('/microsite_company_switch/debug', type='http', auth='user', website=False)
    def debug_info(self, **kw):
        """Endpoint simple para verificar estado del módulo"""
        user = request.env.user
        return f"""
        <h1>Microsite Company Switch - Debug</h1>
        <p>Usuario: {user.name} (ID: {user.id})</p>
        <p>Compañía actual: {user.company_id.name} (ID: {user.company_id.id})</p>
        <p>Cookie cids: {request.httprequest.cookies.get('cids', 'NO SET')}</p>
        <p>Módulo activo: ✅</p>
        """
