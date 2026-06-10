from odoo import models, api
from odoo.fields import Domain
import logging

_logger = logging.getLogger(__name__)

print("[ZONE_FIX] Loading website_mixin.py")

# Monkey-patch _search_build_domain para evitar Domain.AND en zonas
_original_search_build_domain = None

def _patch_search_build_domain():
    global _original_search_build_domain
    from odoo.addons.website.models.mixins import WebsiteSearchableMixin
    
    _original_search_build_domain = WebsiteSearchableMixin._search_build_domain
    
    def _patched_search_build_domain(self, domain_list, search, fields, extra=None):
        # Detectar si el dominio ya está en formato de zona (tiene '&' y tuplas)
        # Esto indica que viene de nuestro _search_get_detail modificado
        is_zone_domain = (
            isinstance(domain_list, list) 
            and len(domain_list) > 0 
            and domain_list[0] == '&'
        )
        
        if is_zone_domain:
            # Para zonas, el dominio ya está construido con expression.AND
            # Solo necesitamos añadir términos de búsqueda si los hay
            if search:
                from odoo.tools import escape_psql
                domain = domain_list
                for search_term in search.split():
                    subdomains = [[(field, 'ilike', escape_psql(search_term))] for field in fields]
                    if extra:
                        extra_domain = extra(self.env, search_term)
                        if extra_domain:
                            subdomains.append(extra_domain)
                    domain = Domain.AND([domain] + subdomains)
                return domain
            # Sin términos de búsqueda, retornar el dominio tal cual
            return domain_list
        
        # No es zona - usar comportamiento original
        return _original_search_build_domain(self, domain_list, search, fields, extra)
    
    WebsiteSearchableMixin._search_build_domain = _patched_search_build_domain
    _logger.info("[ZONE_FIX] Patched _search_build_domain")


_patch_search_build_domain()
