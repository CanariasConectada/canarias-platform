import math
from odoo import http
from odoo.http import request


ZONA_LABELS = {
    'guanarteme': 'Guanarteme',
    'lomolosfrailes': 'Lomo Los Frailes',
    'tamaraceite': 'Tamaraceite',
}


def _build_category_tree(partners):
    """
    Construye un árbol de 3 niveles a partir de x_zca_tipo, x_zca_categoria y x_zca_subcategoria.
    Devuelve una estructura:
    {
        'tipo_val': {
            'label': 'Tipo Label',
            'categorias': {
                'cat_val': {
                    'label': 'Cat Label',
                    'subcategorias': ['Subcat1', 'Subcat2'],
                }
            }
        }
    }
    """
    tree = {}
    for p in partners:
        tipo = (p.x_zca_tipo or '').strip()
        cat = (p.x_zca_categoria or '').strip()
        subcat = (p.x_zca_subcategoria or '').strip()
        if not tipo:
            tipo = 'otros'
        if tipo not in tree:
            tree[tipo] = {'label': tipo.title(), 'categorias': {}}
        if cat:
            if cat not in tree[tipo]['categorias']:
                tree[tipo]['categorias'][cat] = {'label': cat, 'subcategorias': []}
            if subcat and subcat not in tree[tipo]['categorias'][cat]['subcategorias']:
                tree[tipo]['categorias'][cat]['subcategorias'].append(subcat)
    return tree


def _apply_filters(partners, zone=None, tipo=None, category=None, subcategory=None, search=None):
    """Aplica filtros en Python sobre la lista de partners ya leída."""
    result = partners
    if zone:
        result = result.filtered(lambda p: p.x_zca_zona == zone)
    if tipo:
        result = result.filtered(lambda p: (p.x_zca_tipo or '').strip().lower() == tipo.lower())
    if category:
        result = result.filtered(lambda p: (p.x_zca_categoria or '').strip().lower() == category.lower())
    if subcategory:
        result = result.filtered(lambda p: (p.x_zca_subcategoria or '').strip().lower() == subcategory.lower())
    if search and len(search) >= 3:
        search_lower = search.lower()
        result = result.filtered(
            lambda p: search_lower in (p.name or '').lower()
            or search_lower in (p.x_zca_categoria or '').lower()
            or search_lower in (p.x_zca_descripcion_corta or '').lower()
            or search_lower in (p.x_zca_tipo or '').lower()
        )
    return result


class ZcaDirectorioController(http.Controller):

    @http.route('/directorio', type='http', auth='public', website=True)
    def directorio(self, zone=None, tipo=None, category=None, subcategory=None,
                   search=None, view='grid', ppg=21, page=1, **kwargs):
        try:
            ppg = int(ppg)
        except (ValueError, TypeError):
            ppg = 21
        if ppg not in (12, 21, 48):
            ppg = 21
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        Partner = request.env['res.partner'].sudo()
        all_comercios = Partner.search([('x_zca_es_comercio', '=', True)])

        # Árbol de categorías completo (sin filtros) para los selects
        category_tree = _build_category_tree(all_comercios)

        # Filtrado
        filtered = _apply_filters(all_comercios, zone=zone, tipo=tipo,
                                   category=category, subcategory=subcategory,
                                   search=search)

        total = len(filtered)
        page_count = max(1, math.ceil(total / ppg))
        if page > page_count:
            page = page_count

        offset = (page - 1) * ppg
        comercios_page = filtered[offset:offset + ppg]

        # Paginación: lista de páginas a mostrar
        pages = _build_pagination(page, page_count)

        values = {
            'comercios': comercios_page,
            'total': total,
            'category_tree': category_tree,
            'zona_labels': ZONA_LABELS,
            'current_zone': zone or '',
            'current_tipo': tipo or '',
            'current_category': category or '',
            'current_subcategory': subcategory or '',
            'current_search': search or '',
            'view': view if view in ('grid', 'list') else 'grid',
            'ppg': ppg,
            'page': page,
            'page_count': page_count,
            'pages': pages,
        }
        return request.render('zca_platform.directorio_page', values)

    @http.route('/directorio/ajax/search', type='http', auth='public', website=True)
    def directorio_ajax(self, zone=None, tipo=None, category=None, subcategory=None,
                        search=None, view='grid', ppg=21, page=1, **kwargs):
        try:
            ppg = int(ppg)
        except (ValueError, TypeError):
            ppg = 21
        if ppg not in (12, 21, 48):
            ppg = 21
        try:
            page = int(page)
        except (ValueError, TypeError):
            page = 1
        if page < 1:
            page = 1

        Partner = request.env['res.partner'].sudo()
        all_comercios = Partner.search([('x_zca_es_comercio', '=', True)])

        filtered = _apply_filters(all_comercios, zone=zone, tipo=tipo,
                                   category=category, subcategory=subcategory,
                                   search=search)

        total = len(filtered)
        page_count = max(1, math.ceil(total / ppg))
        if page > page_count:
            page = page_count

        offset = (page - 1) * ppg
        comercios_page = filtered[offset:offset + ppg]
        pages = _build_pagination(page, page_count)

        values = {
            'comercios': comercios_page,
            'total': total,
            'current_zone': zone or '',
            'current_tipo': tipo or '',
            'current_category': category or '',
            'current_subcategory': subcategory or '',
            'current_search': search or '',
            'view': view if view in ('grid', 'list') else 'grid',
            'ppg': ppg,
            'page': page,
            'page_count': page_count,
            'pages': pages,
        }
        return request.render('zca_platform.directorio_cards', values)

    @http.route('/directorio/img/<int:partner_id>', type='http', auth='public', website=True)
    def directorio_img(self, partner_id, **kwargs):
        partner = request.env['res.partner'].sudo().browse(partner_id)
        if not partner.exists() or not partner.x_zca_es_comercio:
            return request.not_found()

        image_data = partner.image_1920
        if not image_data:
            return request.not_found()

        import base64
        img_bytes = base64.b64decode(image_data)

        # Detect PNG vs JPEG
        if img_bytes[:4] == b'\x89PNG':
            content_type = 'image/png'
        else:
            content_type = 'image/jpeg'

        headers = [
            ('Content-Type', content_type),
            ('Cache-Control', 'public, max-age=86400'),
            ('Content-Length', str(len(img_bytes))),
        ]
        return request.make_response(img_bytes, headers=headers)


def _build_pagination(current_page, page_count, delta=2):
    """Devuelve lista de números de página y separadores ('...') para mostrar en la UI."""
    if page_count <= 1:
        return []
    pages = []
    left = max(1, current_page - delta)
    right = min(page_count, current_page + delta)

    if left > 1:
        pages.append(1)
        if left > 2:
            pages.append('...')
    for p in range(left, right + 1):
        pages.append(p)
    if right < page_count:
        if right < page_count - 1:
            pages.append('...')
        pages.append(page_count)
    return pages
