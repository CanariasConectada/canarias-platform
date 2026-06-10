from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)

print("[ZONE_FIX] Loading website.py")


class Website(models.Model):
    _inherit = 'website'

    is_canarias_conectada = fields.Boolean(
        string='Es Canarias Conectada',
        compute='_compute_is_canarias_conectada',
        store=False,
    )

    @api.depends('domain')
    def _compute_is_canarias_conectada(self):
        for website in self:
            domain = website.domain or ''
            website.is_canarias_conectada = domain == 'https://canariasconectada.es'

    def get_canarias_categories(self):
        """Retorna categorías públicas según el tipo de website (Canarias, Zona o Microsite)."""
        self.ensure_one()
        
        # Determinar si es Canarias Conectada, Zona o Microsite
        is_canarias = self.is_canarias_conectada
        is_zone = hasattr(self, 'zone_id') and self.zone_id and self.zone_id.id
        # Microsite: website con compañía asignada (no es Canarias ni Zona)
        is_microsite = self.company_id and not is_canarias and not is_zone
        
        _logger.info(f"[ZONE_FIX] get_canarias_categories: website={self.name}, is_canarias={is_canarias}, is_zone={is_zone}, is_microsite={is_microsite}, company_id={self.company_id.id if self.company_id else None}")
        
        if is_zone:
            # ZONA (Guanarteme, Tamaraceite, Lomo): Solo categorías de productos de la zona
            _logger.info(f"[ZONE_FIX] get_canarias_categories: Filtrando por zona {self.zone_id.name}")
            
            # Obtener compañías de la zona
            company_ids = self.env['res.company'].sudo().search([
                ('zone_id', '=', self.zone_id.id)
            ]).ids
            
            if not company_ids:
                return []
            
            # Obtener productos publicados de las compañías de la zona
            products = self.env['product.template'].sudo().search([
                ('sale_ok', '=', True),
                ('is_published', '=', True),
                ('company_id', 'in', company_ids)
            ])
            
            if not products:
                return []
            
            # Obtener IDs únicos de categorías de esos productos
            category_ids = list(set(products.mapped('public_categ_ids').ids))
            if not category_ids:
                return []
            
            _logger.info(f"[ZONE_FIX] Zona {self.zone_id.name}: {len(products)} productos, {len(category_ids)} categorías")
            
            return self.env['product.public.category'].sudo().search([
                ('id', 'in', category_ids)
            ], order='name')
        
        elif is_microsite:
            # MICROSITE: Categorías de los productos de la compañía del website
            _logger.info(f"[ZONE_FIX] get_canarias_categories: Microsite {self.name} - compañía {self.company_id.name} (ID: {self.company_id.id})")
            
            products = self.env['product.template'].sudo().search([
                ('sale_ok', '=', True),
                ('is_published', '=', True),
                ('company_id', '=', self.company_id.id)
            ])
            
            if not products:
                return []
            
            category_ids = list(set(products.mapped('public_categ_ids').ids))
            if not category_ids:
                return []
            
            _logger.info(f"[ZONE_FIX] Microsite {self.name}: {len(products)} productos, {len(category_ids)} categorías")
            
            return self.env['product.public.category'].sudo().search([
                ('id', 'in', category_ids)
            ], order='name')
        
        else:
            # CANARIAS CONECTADA: Todas las categorías de todos los productos
            _logger.info(f"[ZONE_FIX] get_canarias_categories: Canarias Conectada - todas las categorías")
            
            products = self.env['product.template'].sudo().search([
                ('sale_ok', '=', True),
                ('is_published', '=', True)
            ])
            
            if not products:
                return []
            
            category_ids = list(set(products.mapped('public_categ_ids').ids))
            if not category_ids:
                return []
            
            return self.env['product.public.category'].sudo().search([
                ('id', 'in', category_ids)
            ], order='name')


# Monkey-patch para reemplazar completamente el método sale_product_domain
def _patch_sale_product_domain():
    """Reemplaza el método sale_product_domain para zonas y Canarias Conectada."""
    from odoo.addons.website_sale.models.website import Website as WebsiteSaleWebsite
    from odoo.fields import Domain
    
    original_method = WebsiteSaleWebsite.sale_product_domain
    
    def patched_sale_product_domain(self):
        # Manejar caso cuando no hay website o son múltiples
        if not self:
            return original_method(self)
        
        if len(self) > 1:
            return original_method(self)
        
        self.ensure_one()
        
        # Determinar tipo de website
        is_canarias = hasattr(self, 'is_canarias_conectada') and self.is_canarias_conectada
        is_zone = hasattr(self, 'zone_id') and self.zone_id and self.zone_id.id
        
        _logger.info(f"[ZONE_FIX] sale_product_domain called for {self.name}: is_canarias={is_canarias}, is_zone={bool(is_zone)}")
        
        # CASO 1: Canarias Conectada - mostrar TODOS los productos publicados (sin filtro de website_id)
        if is_canarias:
            _logger.info(f"[ZONE_FIX] Canarias Conectada - returning domain without website_id filter")
            if self.env.user._is_internal():
                return Domain.AND([
                    [('sale_ok', '=', True)],
                    [('is_published', '=', True)],
                ])
            else:
                return Domain.AND([
                    [('sale_ok', '=', True)],
                    [('is_published', '=', True)],
                    [('service_tracking', 'in', self.env['product.template']._get_saleable_tracking_types())],
                ])
        
        # CASO 2: Zona comercial - mostrar productos de compañías de la zona (sin filtro de website_id)
        if is_zone:
            _logger.info(f"[ZONE_FIX] Zona {self.zone_id.name} - returning domain with company filter")
            company_ids = self.env['res.company'].sudo().search([
                ('zone_id', '=', self.zone_id.id)
            ]).ids
            
            domain_parts = [
                [('sale_ok', '=', True)],
                [('is_published', '=', True)],
            ]
            
            if not self.env.user._is_internal():
                domain_parts.append([('service_tracking', 'in', self.env['product.template']._get_saleable_tracking_types())])
            
            if company_ids:
                domain_parts.append([('company_id', 'in', company_ids)])
            
            return Domain.AND(domain_parts)
        
        # CASO 3: Microsite individual - comportamiento original (CON filtro de website_id)
        _logger.info(f"[ZONE_FIX] Microsite {self.name} - using original domain with website_id filter")
        return original_method(self)
    
    WebsiteSaleWebsite.sale_product_domain = patched_sale_product_domain
    print("[ZONE_FIX] Patched sale_product_domain successfully")
    _logger.info("[ZONE_FIX] Patched sale_product_domain successfully")


# Aplicar el patch
_patch_sale_product_domain()
