# -*- coding: utf-8 -*-
import json
import logging
import random
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WebsiteDirectory(http.Controller):

    def _get_zone_from_website(self, website):
        """Determina la zona según el dominio del website"""
        if not website or not website.domain:
            return 'canarias'
        domain = website.domain.lower()
        if 'guanarteme' in domain:
            return 'guanarteme'
        elif 'tamaraceite' in domain:
            return 'tamaraceite'
        elif 'frailes' in domain or 'lomolosfrailes' in domain:
            return 'lomolosfrailes'
        return 'canarias'

    # ============================================
    # MÉTODOS PARA SHUFFLE (ORDEN ALEATORIO)
    # ============================================
    
    def _get_or_create_shuffle_seed(self):
        """Obtiene o crea una semilla para el shuffle basada en cookie"""
        if hasattr(request, 'shuffle_seed') and request.shuffle_seed:
            return request.shuffle_seed
        
        seed_str = request.httprequest.cookies.get('directory_seed')
        if seed_str:
            try:
                seed = int(seed_str)
                request.shuffle_seed = seed
                return seed
            except (ValueError, TypeError):
                pass
        
        # Crear nueva semilla
        seed = random.randint(1, 1000000)
        request.shuffle_seed = seed
        request.shuffle_seed_is_new = True
        _logger.info("[DIRECTORY SHUFFLE] Nueva seed creada: %s", seed)
        return seed

    def _apply_shuffle_order(self, records):
        """Aplica orden aleatorio determinístico basado en seed"""
        if not records:
            return records
        
        seed = self._get_or_create_shuffle_seed()
        record_ids = list(records.ids)
        random.Random(seed).shuffle(record_ids)
        return records.browse(record_ids)

    def _set_shuffle_cookie_if_needed(self, response):
        """Setea la cookie de shuffle si es nueva"""
        if hasattr(request, 'shuffle_seed_is_new') and request.shuffle_seed_is_new:
            if hasattr(request, 'shuffle_seed') and request.shuffle_seed:
                response.set_cookie(
                    'directory_seed',
                    str(request.shuffle_seed),
                    max_age=86400,  # 24 horas
                    httponly=True,
                    samesite='Lax'
                )
                _logger.info("[DIRECTORY SHUFFLE] Cookie seteada con seed=%s", request.shuffle_seed)

    def _get_action_company_ids(self, survey_flag, action_key):
        """Devuelve company_ids donde la última evaluación completada tiene answer_score >= 2
        en la pregunta asociada a la acción indicada.

        survey_flag: 'is_sustainability' o 'is_silver_economy'
        action_key: 'energy'|'waste'|'eco' (sostenibilidad) o 'accessible'|'personalized'|'adapted' (silver)
        """
        SUSTAIN_QUESTION_MAP = {
            'energy': ['energ'],
            'waste': ['residuo'],
            'eco': ['ecológ', 'local', 'comunidad'],
        }
        SILVER_ITEM_MAP = {
            'accessible': 'Local accesible',
            'personalized': 'Atención personalizada',
            'adapted': 'Productos o servicios adaptados',
        }
        is_sustain = survey_flag == 'is_sustainability'
        survey_field = 'is_sustainability' if is_sustain else 'is_silver_economy'
        surveys = request.env['survey.survey'].sudo().search([
            (survey_field, '=', True), ('active', '=', True),
        ])
        if not surveys:
            return []
        question_ids = []
        if is_sustain:
            search_terms = SUSTAIN_QUESTION_MAP.get(action_key, [])
            for q in surveys.mapped('question_ids').filtered(lambda q: not q.is_page):
                title = (q.title or '').lower()
                if isinstance(q.title, dict):
                    title = (q.title.get('en_US', '') or q.title.get('es_ES', '') or '').lower()
                if any(t in title for t in search_terms):
                    question_ids.append(q.id)
        else:
            label_search = SILVER_ITEM_MAP.get(action_key, '')
            items = request.env['silver.positive.item'].sudo().search([
                ('survey_id', 'in', surveys.ids),
                ('label', 'ilike', label_search),
            ])
            question_ids = items.mapped('question_id').ids
        if not question_ids:
            return []
        lines = request.env['survey.user_input.line'].sudo().search([
            ('question_id', 'in', question_ids),
            ('answer_score', '>=', 2),
            ('user_input_id.state', '=', 'done'),
            ('user_input_id.test_entry', '=', False),
            ('user_input_id.survey_id.' + survey_field, '=', True),
        ])
        return list(set(lines.mapped('user_input_id.company_id').ids))

    def _get_action_counts(self, base_domain, survey_flag):
        """Calcula conteos de entradas del directorio por acción para un tipo de survey."""
        Entry = request.env['website.directory.entry'].sudo()
        counts = {}
        if survey_flag == 'is_sustainability':
            for action in ('energy', 'waste', 'eco'):
                cids = self._get_action_company_ids(survey_flag, action)
                counts[action] = Entry.search_count(base_domain + [('company_id', 'in', cids)]) if cids else 0
        else:
            for action in ('accessible', 'personalized', 'adapted'):
                cids = self._get_action_company_ids(survey_flag, action)
                counts[action] = Entry.search_count(base_domain + [('company_id', 'in', cids)]) if cids else 0
        return counts

    def _build_domain(self, zone=None, category_id=None, search='', silver_level=None, sustain_action=None, silver_action=None):
        """Construye el dominio de búsqueda"""
        domain = [
            ('active', '=', True),
            ('company_id.show_in_directory', '=', True),
            ('company_id.active', '=', True),
        ]
        
        if zone and zone != 'canarias':
            if zone == 'lomolosfrailes':
                domain.append(('zone', 'in', ['lomolosfrailes', 'lomo_los_frailes', 'lomo los frailes']))
            else:
                domain.append(('zone', '=', zone))
        if category_id:
            all_category_ids = self._get_category_descendants(int(category_id))
            domain.append(('category_ids', 'in', all_category_ids))
        if search:
            domain.extend([
                '|', '|',
                ('name', 'ilike', search),
                ('company_id.partner_id.comercial', 'ilike', search),
                ('company_id.partner_id.name', 'ilike', search),
            ])
        if silver_level and silver_level in ('bronze', 'silver', 'gold'):
            domain.append(('company_id.silver_certification_level', '=', silver_level))
        if sustain_action and sustain_action in ('energy', 'waste', 'eco'):
            cids = self._get_action_company_ids('is_sustainability', sustain_action)
            domain.append(('company_id', 'in', cids))
        if silver_action and silver_action in ('accessible', 'personalized', 'adapted'):
            cids = self._get_action_company_ids('is_silver_economy', silver_action)
            domain.append(('company_id', 'in', cids))
        
        return domain

    def _get_category_descendants(self, category_id):
        """Obtiene todos los IDs descendientes de una categoría (hijos, nietos, etc.) recursivamente"""
        all_ids = [category_id]
        
        def get_children_recursive(cat_ids):
            """Función recursiva para obtener todos los descendientes"""
            if not cat_ids:
                return
            children = request.env['business.category'].sudo().search([
                ('parent_id', 'in', cat_ids),
                ('active', '=', True)
            ])
            if children:
                child_ids = children.ids
                all_ids.extend(child_ids)
                get_children_recursive(child_ids)
        
        # Iniciar recursión con el ID inicial
        get_children_recursive([category_id])
        return list(set(all_ids))  # Eliminar duplicados

    def _get_pagination_values(self, entries_count, page, ppg, url, url_args):
        """Calcula valores de paginación"""
        return request.website.pager(
            url=url,
            total=entries_count,
            page=page,
            step=ppg,
            url_args=url_args
        )

    @http.route(['/directorio', '/directorio/page/<int:page>'], type='http', auth='public', website=True)
    def directory_index(self, page=1, **kw):
        """Página principal del directorio con paginación"""
        try:
            # Handle page parameter from query string (e.g., ?page=1) overriding URL parameter if needed
            if 'page' in kw and kw['page']:
                try:
                    page = int(kw['page'])
                except (ValueError, TypeError):
                    pass  # Keep the URL parameter value
            # Ensure page is int
            page = int(page)
            website = request.website
            current_zone = self._get_zone_from_website(website)
            
            # Parámetros
            category_id = kw.get('category')
            search = kw.get('search', '').strip()
            ppg = int(kw.get('ppg', 21))
            if ppg not in [12, 21, 24, 48]:
                ppg = 21
            
            # Tipo de vista (grid o list)
            view_type = kw.get('view', 'grid')
            if view_type not in ['grid', 'list']:
                view_type = 'grid'
            
            # Filtro Silver Economy
            silver_level = kw.get('silver_level')
            sustain_action = kw.get('sustain_action')
            silver_action = kw.get('silver_action')
            
            domain = self._build_domain(
                zone=current_zone if current_zone != 'canarias' else None,
                category_id=category_id,
                search=search,
                silver_level=silver_level,
                sustain_action=sustain_action,
                silver_action=silver_action,
            )
            
            # Contar y buscar entradas paginadas (con shuffle)
            Entry = request.env['website.directory.entry'].sudo()
            entries_count = Entry.search_count(domain)
            
            # Conteo de empresas por nivel Silver Economy (para botones de filtro)
            base_domain = self._build_domain(
                zone=current_zone if current_zone != 'canarias' else None,
                category_id=category_id,
                search=search
            )
            silver_counts = {
                'gold': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'gold')]),
                'silver': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'silver')]),
                'bronze': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'bronze')]),
            }
            sustain_action_counts = self._get_action_counts(base_domain, 'is_sustainability')
            silver_action_counts = self._get_action_counts(base_domain, 'is_silver_economy')
            offset = (page - 1) * ppg
            
            # Para shuffle: obtenemos todos los IDs del dominio, shuffled, luego paginamos
            all_entry_ids = Entry.search(domain, order='id ASC').ids
            shuffled_ids = self._apply_shuffle_order(Entry.browse(all_entry_ids)).ids
            
            # Paginar los IDs shuffled
            paginated_ids = shuffled_ids[offset:offset + ppg]
            entries = Entry.browse(paginated_ids) if paginated_ids else Entry.browse([])
            
            # Categorías para filtros
            categories = request.env['business.category'].sudo().search([
                ('parent_id', '=', False),
                ('active', '=', True),
            ])
            
            # Preparar datos de categorías para cascada en JSON
            categories_data = []
            for cat in categories:
                cat_data = {'id': cat.id, 'name': cat.name, 'children': []}
                for child in cat.child_ids.filtered(lambda c: c.active):
                    child_data = {'id': child.id, 'name': child.name, 'children': []}
                    for grandchild in child.child_ids.filtered(lambda c: c.active):
                        child_data['children'].append({'id': grandchild.id, 'name': grandchild.name})
                    cat_data['children'].append(child_data)
                categories_data.append(cat_data)
            
            # Generar pager
            pager = self._get_pagination_values(
                entries_count, page, ppg,
                '/directorio',
                {'search': search, 'category': category_id, 'silver_level': silver_level, 'sustain_action': sustain_action, 'silver_action': silver_action}
            )
            
            # Encontrar la categoría seleccionada y sus padres para la cascada
            selected_cat_id = int(category_id) if category_id else None
            selected_cat_parent_id = None
            selected_cat_grandparent_id = None
            
            if selected_cat_id:
                selected_cat = request.env['business.category'].sudo().browse(selected_cat_id)
                if selected_cat.exists():
                    if selected_cat.parent_id:
                        selected_cat_parent_id = selected_cat.parent_id.id
                        if selected_cat.parent_id.parent_id:
                            selected_cat_grandparent_id = selected_cat.parent_id.parent_id.id
                            # Es nivel 3 (nieto)
                        else:
                            # Es nivel 2 (hijo directo)
                            pass  # Ya tenemos parent_id, grandparent_id es None
                    else:
                        # Es nivel 1 (raíz)
                        selected_cat_grandparent_id = selected_cat_id
                        selected_cat_parent_id = None
            
            response = request.render('website_directory.directory_index', {
                'entries': entries,
                'entries_count': entries_count,
                'current_zone': current_zone,
                'categories': categories,
                'categories_json': json.dumps(categories_data),
                'selected_category': selected_cat_id,
                'selected_category_parent': selected_cat_parent_id,
                'selected_category_grandparent': selected_cat_grandparent_id,
                'search': search,
                'pager': pager,
                'ppg': ppg,
                'base_url': '/directorio',
                'view_type': view_type,
                'page': page,
                'silver_level': silver_level,
                'silver_counts': silver_counts,
                'sustain_action': sustain_action,
                'silver_action': silver_action,
                'sustain_action_counts': sustain_action_counts,
                'silver_action_counts': silver_action_counts,
            })
            
            # Setear cookie de shuffle si es nueva
            self._set_shuffle_cookie_if_needed(response)
            return response
            
        except Exception as e:
            _logger.error("Error en directorio: %s", str(e))
            return request.render('website.page_404', {})

    @http.route(['/directorio/zona/<string:zone>', '/directorio/zona/<string:zone>/page/<int:page>'], 
                type='http', auth='public', website=True)
    def directory_by_zone(self, zone=None, page=1, **kw):
        """Filtrar directorio por zona específica con paginación"""
        try:
            search = kw.get('search', '').strip()
            category_id = kw.get('category')
            ppg = int(kw.get('ppg', 21))
            if ppg not in [12, 21, 24, 48]:
                ppg = 21
            
            view_type = kw.get('view', 'grid')
            if view_type not in ['grid', 'list']:
                view_type = 'grid'
            
            silver_level = kw.get('silver_level')
            sustain_action = kw.get('sustain_action')
            silver_action = kw.get('silver_action')
            
            domain = self._build_domain(zone=zone, category_id=category_id, search=search, silver_level=silver_level, sustain_action=sustain_action, silver_action=silver_action)
            
            Entry = request.env['website.directory.entry'].sudo()
            entries_count = Entry.search_count(domain)
            
            # Conteo de empresas por nivel Silver Economy (para botones de filtro)
            base_domain = self._build_domain(zone=zone, category_id=category_id, search=search)
            silver_counts = {
                'gold': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'gold')]),
                'silver': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'silver')]),
                'bronze': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'bronze')]),
            }
            offset = (page - 1) * ppg
            
            # Para shuffle: obtenemos todos los IDs del dominio, shuffled, luego paginamos
            all_entry_ids = Entry.search(domain, order='id ASC').ids
            shuffled_ids = self._apply_shuffle_order(Entry.browse(all_entry_ids)).ids
            
            # Paginar los IDs shuffled
            paginated_ids = shuffled_ids[offset:offset + ppg]
            entries = Entry.browse(paginated_ids) if paginated_ids else Entry.browse([])
            
            categories = request.env['business.category'].sudo().search([
                ('parent_id', '=', False),
                ('active', '=', True),
            ])
            
            # Preparar datos de categorías para cascada
            categories_data = []
            for cat in categories:
                cat_data = {'id': cat.id, 'name': cat.name, 'children': []}
                for child in cat.child_ids.filtered(lambda c: c.active):
                    child_data = {'id': child.id, 'name': child.name, 'children': []}
                    for grandchild in child.child_ids.filtered(lambda c: c.active):
                        child_data['children'].append({'id': grandchild.id, 'name': grandchild.name})
                    cat_data['children'].append(child_data)
                categories_data.append(cat_data)
            
            pager = self._get_pagination_values(
                entries_count, page, ppg,
                f'/directorio/zona/{zone}',
                {'search': search, 'category': category_id, 'silver_level': silver_level, 'sustain_action': sustain_action, 'silver_action': silver_action}
            )
            
            response = request.render('website_directory.directory_index', {
                'entries': entries,
                'entries_count': entries_count,
                'current_zone': zone,
                'categories': categories,
                'categories_json': json.dumps(categories_data),
                'selected_category': int(category_id) if category_id else None,
                'selected_category_parent': None,
                'selected_category_grandparent': None,
                'search': search,
                'pager': pager,
                'ppg': ppg,
                'filter_zone': True,
                'base_url': f'/directorio/zona/{zone}',
                'view_type': view_type,
                'page': page,
                'silver_level': silver_level,
                'silver_counts': silver_counts,
                'sustain_action': sustain_action,
                'silver_action': silver_action,
                'sustain_action_counts': sustain_action_counts,
                'silver_action_counts': silver_action_counts,
            })
            
            # Setear cookie de shuffle si es nueva
            self._set_shuffle_cookie_if_needed(response)
            return response
            
        except Exception as e:
            _logger.error("Error en directorio por zona: %s", str(e))
            return request.render('website.page_404', {})

    @http.route(['/directorio/categoria/<int:category_id>', 
                 '/directorio/categoria/<int:category_id>/page/<int:page>'], 
                type='http', auth='public', website=True)
    def directory_by_category(self, category_id=None, page=1, **kw):
        """Filtrar directorio por categoría con paginación"""
        try:
            website = request.website
            current_zone = self._get_zone_from_website(website)
            search = kw.get('search', '').strip()
            ppg = int(kw.get('ppg', 21))
            if ppg not in [12, 21, 24, 48]:
                ppg = 21
            
            view_type = kw.get('view', 'grid')
            if view_type not in ['grid', 'list']:
                view_type = 'grid'
            
            silver_level = kw.get('silver_level')
            sustain_action = kw.get('sustain_action')
            silver_action = kw.get('silver_action')
            
            domain = self._build_domain(
                zone=current_zone if current_zone != 'canarias' else None,
                category_id=category_id,
                search=search,
                silver_level=silver_level,
                sustain_action=sustain_action,
                silver_action=silver_action,
            )
            
            Entry = request.env['website.directory.entry'].sudo()
            entries_count = Entry.search_count(domain)
            
            # Conteo de empresas por nivel Silver Economy (para botones de filtro)
            base_domain = self._build_domain(
                zone=current_zone if current_zone != 'canarias' else None,
                category_id=category_id,
                search=search
            )
            silver_counts = {
                'gold': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'gold')]),
                'silver': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'silver')]),
                'bronze': Entry.search_count(base_domain + [('company_id.silver_certification_level', '=', 'bronze')]),
            }
            sustain_action_counts = self._get_action_counts(base_domain, 'is_sustainability')
            silver_action_counts = self._get_action_counts(base_domain, 'is_silver_economy')
            offset = (page - 1) * ppg
            
            # Para shuffle: obtenemos todos los IDs del dominio, shuffled, luego paginamos
            all_entry_ids = Entry.search(domain, order='id ASC').ids
            shuffled_ids = self._apply_shuffle_order(Entry.browse(all_entry_ids)).ids
            
            # Paginar los IDs shuffled
            paginated_ids = shuffled_ids[offset:offset + ppg]
            entries = Entry.browse(paginated_ids) if paginated_ids else Entry.browse([])
            
            category = request.env['business.category'].sudo().browse(category_id)
            
            categories = request.env['business.category'].sudo().search([
                ('parent_id', '=', False),
                ('active', '=', True),
            ])
            
            pager = self._get_pagination_values(
                entries_count, page, ppg,
                f'/directorio/categoria/{category_id}',
                {'search': search, 'silver_level': silver_level, 'sustain_action': sustain_action, 'silver_action': silver_action}
            )
            
            # Preparar datos de categorías para cascada
            categories_data = []
            for cat in categories:
                cat_data = {'id': cat.id, 'name': cat.name, 'children': []}
                for child in cat.child_ids.filtered(lambda c: c.active):
                    child_data = {'id': child.id, 'name': child.name, 'children': []}
                    for grandchild in child.child_ids.filtered(lambda c: c.active):
                        child_data['children'].append({'id': grandchild.id, 'name': grandchild.name})
                    cat_data['children'].append(child_data)
                categories_data.append(cat_data)
            
            response = request.render('website_directory.directory_index', {
                'entries': entries,
                'entries_count': entries_count,
                'current_zone': current_zone,
                'categories': categories,
                'categories_json': json.dumps(categories_data),
                'selected_category': category_id,
                'selected_category_parent': None,
                'selected_category_grandparent': None,
                'filter_category': category,
                'search': search,
                'pager': pager,
                'ppg': ppg,
                'base_url': f'/directorio/categoria/{category_id}',
                'view_type': view_type,
                'page': page,
                'silver_level': silver_level,
                'silver_counts': silver_counts,
                'sustain_action': sustain_action,
                'silver_action': silver_action,
                'sustain_action_counts': sustain_action_counts,
                'silver_action_counts': silver_action_counts,
            })
            
            # Setear cookie de shuffle si es nueva
            self._set_shuffle_cookie_if_needed(response)
            return response
            
        except Exception as e:
            _logger.error("Error en directorio por categoría: %s", str(e))
            return request.render('website.page_404', {})

    @http.route('/directorio/ajax/search', type='http', auth='public', website=True, methods=['GET', 'POST'])
    def directory_ajax_search(self, **kw):
        """Búsqueda AJAX asíncrona para el directorio"""
        try:
            website = request.website
            current_zone = self._get_zone_from_website(website)
            
            search = kw.get('search', '').strip()
            category_id = kw.get('category')
            view_type = kw.get('view', 'grid')
            page = int(kw.get('page', 1))
            ppg = int(kw.get('ppg', 21))
            silver_level = kw.get('silver_level')
            sustain_action = kw.get('sustain_action')
            silver_action = kw.get('silver_action')
            
            # Build domain for search - always include zone filter
            domain = self._build_domain(
                zone=current_zone if current_zone != 'canarias' else None,
                category_id=category_id,
                search=search,
                silver_level=silver_level,
                sustain_action=sustain_action,
                silver_action=silver_action,
            )
            
            Entry = request.env['website.directory.entry'].sudo()
            entries_count = Entry.search_count(domain)
            offset = (page - 1) * ppg
            
            # Para shuffle: obtenemos todos los IDs del dominio, shuffled, luego paginamos
            all_entry_ids = Entry.search(domain, order='id ASC').ids
            shuffled_ids = self._apply_shuffle_order(Entry.browse(all_entry_ids)).ids
            
            # Paginar los IDs shuffled
            paginated_ids = shuffled_ids[offset:offset + ppg]
            entries = Entry.browse(paginated_ids) if paginated_ids else Entry.browse([])
            
            # Generate pager for AJAX
            pager = request.website.pager(
                url='/directorio',
                total=entries_count,
                page=page,
                step=ppg,
                url_args={'search': search, 'category': category_id, 'view': view_type, 'ppg': ppg, 'silver_level': silver_level, 'sustain_action': sustain_action, 'silver_action': silver_action}
            )
            
            response = request.render('website_directory.directory_search_results', {
                'entries': entries,
                'entries_count': entries_count,
                'search': search,
                'view_type': view_type,
                'page': page,
                'current_zone': current_zone,
                'pager': pager,
                'ppg': ppg,
                'category_id': category_id,
                'silver_level': silver_level,
                'sustain_action': sustain_action,
                'silver_action': silver_action,
            })
            
            # Setear cookie de shuffle si es nueva
            self._set_shuffle_cookie_if_needed(response)
            return response
            
        except Exception as e:
            _logger.error("Error en búsqueda AJAX: %s", str(e))
            return request.render('website_directory.directory_search_results', {
                'entries': [],
                'entries_count': 0,
                'search': kw.get('search', ''),
                'view_type': 'grid',
                'silver_level': kw.get('silver_level', ''),
                'sustain_action': kw.get('sustain_action', ''),
                'silver_action': kw.get('silver_action', ''),
                'ppg': kw.get('ppg', 21),
                'category_id': kw.get('category', ''),
            })

    @http.route('/directorio/img/<int:entry_id>', type='http', auth='public', website=True)
    def directory_image(self, entry_id, **kw):
        """Servir imagen de empresa públicamente"""
        try:
            entry = request.env['website.directory.entry'].sudo().browse(entry_id)
            if not entry.exists() or not entry.is_published:
                return request.not_found()
            
            import base64
            image_data = None
            
            # Prioridad 1: Imagen propia del entry
            if entry.image:
                image_data = entry.image
            # Prioridad 2: Logo de la compañía (usar logo_web que está optimizado)
            elif entry.company_id and entry.company_id.logo_web:
                image_data = entry.company_id.logo_web
            
            if image_data:
                return request.make_response(
                    base64.b64decode(image_data),
                    headers=[
                        ('Content-Type', 'image/png'),
                        ('Cache-Control', 'public, max-age=86400'),
                    ]
                )
            else:
                return request.not_found()
                
        except Exception as e:
            _logger.error("Error sirviendo imagen: %s", str(e))
            return request.not_found()
