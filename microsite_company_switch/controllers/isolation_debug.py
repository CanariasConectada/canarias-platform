# -*- coding: utf-8 -*-
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class IsolationDebugController(http.Controller):
    """
    Controlador para debug del aislamiento de compañías.
    Permite verificar el estado del aislamiento desde el frontend.
    """

    @http.route('/microsite_company_switch/debug/isolation', type='jsonrpc', auth='user', methods=['POST'])
    def debug_isolation(self, **kwargs):
        """Retorna información de debug sobre el aislamiento actual"""
        try:
            user = request.env.user
            context = request.env.context or {}
            
            # Información del usuario
            user_info = {
                'id': user.id,
                'name': user.name,
                'login': user.login,
                'is_public': user._is_public(),
                'company_id': user.company_id.id if user.company_id else None,
                'company_name': user.company_id.name if user.company_id else None,
            }
            
            # Compañías del usuario
            user_companies = [
                {'id': c.id, 'name': c.name} 
                for c in user.company_ids
            ]
            
            # Contexto actual
            context_info = {
                'allowed_company_ids': context.get('allowed_company_ids', []),
                'company_id': context.get('company_id'),
            }
            
            # Cookie
            cookie_cids = request.httprequest.cookies.get('cids', '')
            
            # Contar contactos visibles
            Partner = request.env['res.partner']
            try:
                # Esto aplicará las reglas de seguridad
                visible_partners = Partner.search([], limit=100)
                partners_info = [
                    {'id': p.id, 'name': p.name, 'company_id': p.company_id.id if p.company_id else None}
                    for p in visible_partners[:20]  # Solo primeros 20
                ]
                total_partners = Partner.search_count([])
            except Exception as e:
                partners_info = []
                total_partners = 0
                _logger.error(f"[MCS-DEBUG] Error buscando partners: {e}")
            
            result = {
                'status': 'success',
                'user': user_info,
                'user_companies': user_companies,
                'context': context_info,
                'cookie_cids': cookie_cids,
                'partners': {
                    'sample': partners_info,
                    'total_visible': total_partners,
                },
                'isolation_status': {
                    'strict_mode': True,
                    'allowed_companies_count': len(context_info['allowed_company_ids'] or []),
                    'is_isolated': len(context_info['allowed_company_ids'] or []) == 1,
                }
            }
            
            _logger.info(f"[MCS-DEBUG] Debug isolation llamado: {result}")
            return result
            
        except Exception as e:
            _logger.error(f"[MCS-DEBUG] Error en debug_isolation: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
            }

    @http.route('/microsite_company_switch/debug/rules', type='jsonrpc', auth='user', methods=['POST'])
    def debug_rules(self, **kwargs):
        """Retorna información sobre las reglas de seguridad activas"""
        try:
            Rule = request.env['ir.rule']
            rules = Rule.search([('model_id.model', '=', 'res.partner')])
            
            rules_info = []
            for rule in rules:
                rules_info.append({
                    'id': rule.id,
                    'name': rule.name,
                    'active': rule.active,
                    'domain': rule.domain_force,
                    'groups': [g.name for g in rule.groups] if rule.groups else ['GLOBAL'],
                })
            
            return {
                'status': 'success',
                'rules': rules_info,
            }
            
        except Exception as e:
            _logger.error(f"[MCS-DEBUG] Error en debug_rules: {e}", exc_info=True)
            return {
                'status': 'error',
                'message': str(e),
            }
