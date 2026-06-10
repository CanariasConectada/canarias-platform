import json
import math
from odoo import http
from odoo.http import request


class ZcaMainController(http.Controller):

    @http.route('/shop/ajax/products', type='http', auth='public', website=True)
    def shop_ajax_products(self, category_id=None, search=None,
                           min_price=None, max_price=None,
                           page=1, ppg=20, **kwargs):
        """
        Devuelve productos de TODOS los websites mezclados en JSON.
        Útil para un shop unificado de la plataforma ZCA.
        """
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1
        try:
            ppg = int(ppg)
        except (ValueError, TypeError):
            ppg = 20
        if ppg > 100:
            ppg = 100

        domain = [
            ('sale_ok', '=', True),
            ('website_published', '=', True),
        ]

        if search:
            domain += [('name', 'ilike', search)]

        if category_id:
            try:
                cat_id = int(category_id)
                domain += [('public_categ_ids', 'child_of', cat_id)]
            except (ValueError, TypeError):
                pass

        # Precio mínimo / máximo
        if min_price:
            try:
                domain += [('list_price', '>=', float(min_price))]
            except (ValueError, TypeError):
                pass
        if max_price:
            try:
                domain += [('list_price', '<=', float(max_price))]
            except (ValueError, TypeError):
                pass

        # Leer productos de todos los websites con sudo
        Product = request.env['product.template'].sudo()
        all_products = Product.search(domain, order='name asc')

        total = len(all_products)
        page_count = max(1, math.ceil(total / ppg))
        if page > page_count:
            page = page_count

        offset = (page - 1) * ppg
        products_page = all_products[offset:offset + ppg]

        base_url = request.httprequest.host_url.rstrip('/')

        result = []
        for p in products_page:
            # Determinar la URL del comercio dueño del producto
            comercio_url = ''
            if p.company_id:
                partner = request.env['res.partner'].sudo().search(
                    [('company_id', '=', p.company_id.id),
                     ('x_zca_es_comercio', '=', True)],
                    limit=1
                )
                if partner and partner.x_zca_microsite_url:
                    comercio_url = partner.x_zca_microsite_url

            # Imagen
            image_url = f'{base_url}/web/image/product.template/{p.id}/image_128'

            # Categorías públicas (primer nivel)
            categories = [c.name for c in p.public_categ_ids]

            result.append({
                'id': p.id,
                'name': p.name,
                'price': p.list_price,
                'currency': p.currency_id.name if p.currency_id else 'EUR',
                'image_url': image_url,
                'website_url': comercio_url or f'{base_url}/shop/product/{p.id}',
                'category': ', '.join(categories) if categories else '',
                'company': p.company_id.name if p.company_id else '',
            })

        response_data = {
            'products': result,
            'total': total,
            'page': page,
            'page_count': page_count,
            'ppg': ppg,
        }

        headers = [
            ('Content-Type', 'application/json'),
            ('Cache-Control', 'no-cache'),
        ]
        return request.make_response(
            json.dumps(response_data, ensure_ascii=False),
            headers=headers,
        )
