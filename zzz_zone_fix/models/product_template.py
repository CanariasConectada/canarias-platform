from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

print("[ZONE_FIX] Loading product_template.py")

class ProductTemplate(models.Model):
    _inherit = 'product.template'
    
    @api.model
    def _search_get_detail(self, website, order, options):
        """Solo modifica el orden, NO el dominio para evitar conflictos con Odoo 19."""
        # Llamar al método original
        result = super(ProductTemplate, self)._search_get_detail(website, order, options)
        
        # Solo modificar el orden para Canarias/Zonas
        is_canarias = hasattr(website, 'is_canarias_conectada') and website.is_canarias_conectada
        is_zone = hasattr(website, 'zone_id') and website.zone_id and website.zone_id.id
        
        if is_canarias or is_zone:
            # Forzar orden aleatorio por defecto
            if not order or order == 'website_sequence ASC':
                result['order'] = 'random()'
            result['requires_sudo'] = True
        
        return result


# Monkey-patch para _search_fetch donde sí podemos controlar el dominio
_original_search_fetch = None

def _patch_search_fetch():
    global _original_search_fetch
    from odoo.addons.website.models.mixins import WebsiteSearchableMixin
    
    _original_search_fetch = WebsiteSearchableMixin._search_fetch
    
    def _patched_search_fetch(self, search_detail, search, limit, order):
        website = self.env['website'].get_current_website()
        
        # Solo aplicar a product.template
        if self._name != 'product.template':
            return _original_search_fetch(self, search_detail, search, limit, order)
        
        # Verificar si es zona/Canarias
        is_canarias = hasattr(website, 'is_canarias_conectada') and website.is_canarias_conectada
        is_zone = hasattr(website, 'zone_id') and website.zone_id and website.zone_id.id
        
        if is_canarias or is_zone:
            print(f"[ZONE_FIX] INTERCEPT: website={website.name}, is_canarias={is_canarias}, is_zone={bool(is_zone)}", flush=True)
            
            # Construir dominio base simple
            if is_zone:
                company_ids = self.env['res.company'].sudo().search([
                    ('zone_id', '=', website.zone_id.id)
                ]).ids
                base_domain = [('sale_ok', '=', True), ('is_published', '=', True)]
                if company_ids:
                    base_domain.append(('company_id', 'in', company_ids))
                else:
                    base_domain = [('id', '=', False)]
            else:  # is_canarias
                base_domain = [('sale_ok', '=', True), ('is_published', '=', True)]
            
            # Construir dominio de búsqueda
            fields = search_detail['search_fields']
            domain = list(base_domain)
            
            if search:
                from odoo.tools import escape_psql
                search_terms = search.split()
                for term in search_terms:
                    term_conditions = []
                    for field in fields:
                        term_conditions.append((field, 'ilike', escape_psql(term)))
                    if term_conditions:
                        # Añadir OR de condiciones de este término
                        domain = ['|'] * (len(term_conditions) - 1) + domain + term_conditions
            
            model = self.sudo()
            
            # Determinar orden
            final_order = order or search_detail.get('order')
            use_random = not final_order or 'website_sequence' in str(final_order)
            
            if use_random:
                final_order = 'RANDOM()'
            
            print(f"[ZONE_FIX] Using order: {final_order}, random={use_random}", flush=True)
            
            # Búsqueda con orden aleatorio diario
            if use_random:
                all_ids = model.search(domain, limit=None, order='id').ids
                
                import random
                from datetime import date
                daily_seed = int(date.today().strftime('%Y%m%d'))
                random.Random(daily_seed).shuffle(all_ids)
                
                if limit:
                    all_ids = all_ids[:limit]
                
                results = model.browse(all_ids)
                count = len(all_ids)
                print(f"[ZONE_FIX] Random results: {count} products", flush=True)
            else:
                results = model.search(domain, limit=limit, order=final_order)
                count = model.search_count(domain) if limit and len(results) == limit else len(results)
            
            return results, count
        
        # Comportamiento normal
        return _original_search_fetch(self, search_detail, search, limit, order)
    
    WebsiteSearchableMixin._search_fetch = _patched_search_fetch
    _logger.info("[ZONE_FIX] Patched _search_fetch")


_patch_search_fetch()


# Patch para _shop_lookup_products - solo debug, no modificar retorno
def _patch_shop_lookup_products():
    # No aplicar patch por ahora para evitar conflictos
    pass

_patch_shop_lookup_products()
