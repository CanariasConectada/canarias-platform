# -*- coding: utf-8 -*-
"""
Búsqueda asíncrona para la tienda (/shop)
Similar a la del directorio
"""
from odoo import http
from odoo.http import request
from odoo.addons.website_sale.controllers.main import TableCompute
import logging

_logger = logging.getLogger(__name__)


class ShopAsyncSearch(http.Controller):
    """Controller para búsqueda asíncrona en la tienda"""

    @http.route('/shop/search_async', type='jsonrpc', auth='public', website=True)
    def shop_search_async(self, search='', category=None, zone=None, page=1, **kw):
        """
        Búsqueda asíncrona de productos
        Devuelve HTML parcial para actualizar el grid de productos
        """
        try:
            # Obtener website actual
            website = request.website
            page = int(page) if page else 1
            
            # Configuración de grid (productos por página y fila)
            ppg = website.shop_ppg or 21  # Productos por página
            ppr = website.shop_ppr or 4   # Productos por fila
            gap = website.shop_gap or "16px"
            
            # Preparar dominio base
            domain = [('sale_ok', '=', True), ('is_published', '=', True)]
            
            # Filtro de búsqueda
            if search:
                domain.append(('name', 'ilike', search))
            
            # Filtro de categoría
            if category:
                try:
                    category_id = int(category)
                    domain.append(('public_categ_ids', 'in', [category_id]))
                except (ValueError, TypeError):
                    pass
            
            # CASO 1: Canarias Conectada - mostrar TODOS los productos (sin filtro adicional)
            if website.is_canarias_conectada:
                _logger.info(f"[ShopAsyncSearch] Canarias Conectada - mostrando todos los productos")
            # CASO 2: Microsite con zona - filtrar por compañías de la zona
            elif zone or website.zone_id:
                zone_code = zone or (website.zone_id.code if website.zone_id else None)
                if zone_code:
                    company_ids = website._get_zone_company_ids()
                    if company_ids:
                        domain.append(('company_id', 'in', company_ids))
                        _logger.info(f"[ShopAsyncSearch] Zona {zone_code} - filtrando por compañías: {company_ids}")
            # CASO 3: Microsite individual sin zona - filtrar SOLO por su compañía
            else:
                domain.append(('company_id', '=', website.company_id.id))
                _logger.info(f"[ShopAsyncSearch] Microsite individual {website.name} - filtrando por company_id={website.company_id.id}")
            
            # Contar total para paginación
            ProductTemplate = request.env['product.template'].sudo()
            total_products = ProductTemplate.search_count(domain)
            
            # Calcular offset
            offset = (page - 1) * ppg
            
            # Buscar productos
            products = ProductTemplate.search(domain, limit=ppg, offset=offset)
            
            # Usar TableCompute para generar la estructura del grid
            table_compute = TableCompute()
            bins = table_compute.process(products, ppg, ppr)
            
            # Preparar valores para el template
            render_values = {
                'products': products,
                'bins': bins,
                'search': search,
                'website': website,
                'products_count': total_products,
                'page': page,
                'ppg': ppg,
                'ppr': ppr,
                'gap': gap,
                'hasLeftColumn': True,  # Asumimos sidebar
                'grid_block_name': 'Product',
                'product_block_name': 'Product',
            }
            
            # Renderizar el template de grid de productos
            html = request.env['ir.ui.view']._render_template(
                'microsite_zones.shop_products_grid_async',
                render_values
            )
            
            return {
                'success': True,
                'html': html,
                'products_count': total_products,
            }
            
        except Exception as e:
            _logger.error(f"[ShopAsyncSearch] Error: {e}")
            import traceback
            _logger.error(traceback.format_exc())
            return {
                'success': False,
                'error': str(e),
            }
