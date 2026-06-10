import logging
from odoo import http
from odoo.http import request

# Intentar importar desde microsite_zones si está disponible
try:
    from odoo.addons.microsite_zones.controllers.main import WebsiteSaleZones as WebsiteSaleBase
    _logger = logging.getLogger(__name__)
    _logger.info("[ZONE_FIX] Usando WebsiteSaleZones como base")
except ImportError:
    from odoo.addons.website_sale.controllers.main import WebsiteSale as WebsiteSaleBase
    _logger = logging.getLogger(__name__)
    _logger.info("[ZONE_FIX] Usando WebsiteSale como base (microsite_zones no disponible)")


class WebsiteSaleCanarias(WebsiteSaleBase):
    """
    Controlador para Canarias Conectada y Zonas Comerciales.
    Asegura el filtrado por categoría y por zona.
    """

    @http.route(['/shop/validate_category'], type='json', auth='public', website=True)
    def validate_category_access(self, category_id=None, **kwargs):
        """
        Valida si una categoría es accesible en el website actual.
        Usado por el JavaScript para verificar antes de navegar.
        """
        if not category_id:
            return {'valid': False}
        
        website = request.website
        try:
            category = request.env['product.public.category'].sudo().browse(int(category_id))
            if not category.exists():
                return {'valid': False}
            
            # Verificar si hay productos de esta categoría en el website
            products = request.env['product.template'].sudo().search([
                ('sale_ok', '=', True),
                ('is_published', '=', True),
                ('public_categ_ids', 'in', [category.id]),
            ])
            
            return {'valid': bool(products), 'category_name': category.name}
        except Exception as e:
            _logger.error(f"[ZONE_FIX] Error validando categoria: {e}")
            return {'valid': False}

    def _shop_lookup_products(self, options, post, search, website):
        """
        Sobrescribe para asegurar que el filtrado funcione correctamente.
        """
        # Verificar tipo de website
        is_canarias = hasattr(website, 'is_canarias_conectada') and website.is_canarias_conectada
        is_zone = hasattr(website, 'zone_id') and website.zone_id
        
        _logger.info(f"[ZONE_FIX] _shop_lookup_products - website: {website.name}, is_canarias: {is_canarias}, is_zone: {is_zone}")
        
        # Llamar al método padre (ahora WebsiteSaleZones si está disponible)
        fuzzy_search_term, product_count, search_result = super(WebsiteSaleCanarias, self)._shop_lookup_products(
            options, post, search, website
        )
        
        # FILTRO POR ZONA: Si estamos en una zona, solo mostrar productos de esa zona
        # NOTA: Este filtro ya lo hace microsite_zones, pero lo mantenemos por si acaso
        if is_zone and not search_result:  # Solo si no hay resultados
            company_ids = request.env['res.company'].sudo().search([
                ('zone_id', '=', website.zone_id.id)
            ]).ids
            
            if company_ids:
                filtered_by_zone = search_result.filtered(
                    lambda p: p.company_id.id in company_ids
                )
                _logger.info(f"[ZONE_FIX] Zona {website.zone_id.name}: {len(search_result)} -> {len(filtered_by_zone)} productos")
                search_result = filtered_by_zone
                product_count = len(search_result)
        
        # FILTRO POR CATEGORÍA: Aplicar si hay categoría seleccionada
        if (is_canarias or is_zone) and options.get('category'):
            category_id = options.get('category')
            try:
                category_id = int(category_id)
                filtered_by_category = search_result.filtered(
                    lambda p: category_id in p.public_categ_ids.ids
                )
                _logger.info(f"[ZONE_FIX] Filtro categoria {category_id}: {len(search_result)} -> {len(filtered_by_category)} productos")
                search_result = filtered_by_category
                product_count = len(search_result)
            except (ValueError, TypeError) as e:
                _logger.error(f"[ZONE_FIX] Error convirtiendo categoria: {e}")
        
        return fuzzy_search_term, product_count, search_result


    @http.route('/shop/ajax/products', type='http', auth='public', website=True, csrf=False)
    def shop_ajax_products(self, category=None, search='', min_price=0.0, max_price=0.0, **post):
        """
        Endpoint AJAX para cargar productos filtrados sin recargar la página.
        Devuelve JSON con el HTML renderizado del grid de productos.
        """
        import json
        
        website = request.website
        
        # Verificar tipo de website (pero permitir si viene de un contexto válido)
        is_canarias = hasattr(website, 'is_canarias_conectada') and website.is_canarias_conectada
        is_zone = hasattr(website, 'zone_id') and website.zone_id
        
        _logger.info(f"[ZONE_FIX AJAX] Website: {website.name}, is_canarias={is_canarias}, is_zone={is_zone}")
        _logger.info(f"[ZONE_FIX AJAX] category={category}, search={search}, min_price={min_price}, max_price={max_price}")
        
        try:
            # Preparar opciones para la búsqueda
            options = self._get_shop_options(search, category, min_price, max_price, **post)
            
            # Obtener productos filtrados
            fuzzy_search_term, product_count, search_result = self._shop_lookup_products(
                options, post, search, website
            )
            
            # Aplicar filtro de precio adicional si es necesario
            if min_price or max_price:
                try:
                    min_p = float(min_price) if min_price else 0.0
                    max_p = float(max_price) if max_price else 0.0
                    
                    if min_p > 0 or max_p > 0:
                        # Filtrar por precio (usando list_price)
                        filtered = search_result
                        if min_p > 0:
                            filtered = filtered.filtered(lambda p: p.list_price >= min_p)
                        if max_p > 0:
                            filtered = filtered.filtered(lambda p: p.list_price <= max_p)
                        
                        _logger.info(f"[ZONE_FIX AJAX] Filtro precio {min_p}-{max_p}: {len(search_result)} -> {len(filtered)} productos")
                        search_result = filtered
                        product_count = len(search_result)
                except (ValueError, TypeError) as e:
                    _logger.error(f"[ZONE_FIX AJAX] Error filtro precio: {e}")
            
            # Preparar datos para el template
            products = search_result
            
            # Obtener atributos y categorías para el contexto
            attrib_list = request.httprequest.args.getlist('attrib')
            attrib_values = [[int(x) for x in v.split("-")] for v in attrib_list if v]
            
            # Función helper para obtener precios (compatible con el template)
            def get_product_prices(product):
                return {
                    'price_reduce': product.list_price or 0,
                    'base_price': product.list_price or 0,
                }
            
            # Renderizar solo el grid de productos
            html = request.env['ir.ui.view']._render_template(
                'zzz_zone_fix.products_grid_ajax',
                {
                    'products': products,
                    'product_count': product_count,
                    'category': category and request.env['product.public.category'].browse(int(category)) or None,
                    'website': website,
                    'search': search,
                    'attrib_values': attrib_values,
                    'get_product_prices': get_product_prices,
                }
            )
            
            # Calcular rango de precios para el indicador
            price_info = {}
            if min_price or max_price:
                price_info = {
                    'min': float(min_price) if min_price else 0,
                    'max': float(max_price) if max_price else 0,
                }
            
            # Obtener nombre de la categoría si existe
            category_name = None
            if category:
                category_obj = request.env['product.public.category'].sudo().browse(int(category))
                if category_obj.exists():
                    category_name = category_obj.name
            
            return request.make_response(
                json.dumps({
                    'html': html.decode('utf-8') if isinstance(html, bytes) else html,
                    'count': product_count,
                    'category_id': category and int(category) or None,
                    'category_name': category_name,
                    'search': search,
                    'price': price_info,
                    'filters_active': bool(category or search or min_price or max_price),
                }),
                headers=[('Content-Type', 'application/json')]
            )
            
        except Exception as e:
            _logger.error(f"[ZONE_FIX AJAX] Error: {e}")
            return request.make_response(
                json.dumps({'error': str(e)}),
                headers=[('Content-Type', 'application/json')]
            )
    
    def _get_shop_options(self, search, category, min_price=0.0, max_price=0.0, **post):
        """Helper para preparar opciones de búsqueda."""
        return {
            'displayDescription': True,
            'displayDetail': True,
            'displayExtraDetail': True,
            'displayExtraLink': True,
            'displayImage': True,
            'displayName': True,
            'allowFuzzy': True,
            'category': str(category) if category else None,
            'tags': [],
            'min_price': float(min_price) if min_price else 0.0,
            'max_price': float(max_price) if max_price else 0.0,
            'attrib': [],
            'display_currency': None,
        }
