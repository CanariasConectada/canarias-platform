# -*- coding: utf-8 -*-
import werkzeug
from odoo import http
from odoo.http import request
from markupsafe import Markup
import base64
import json
import werkzeug
from datetime import datetime
from PIL import Image
import io


def procesar_imagen_webp(image_data, max_width=1600, max_height=1200, quality=90):
    """
    Procesa imagen: convierte a WebP con redimensionamiento proporcional.
    
    Args:
        image_data: bytes o base64 de la imagen
        max_width: ancho máximo
        max_height: alto máximo  
        quality: calidad WebP (1-100)
    
    Returns:
        base64 de la imagen procesada en WebP
    """
    # Decodificar base64 si es necesario
    if isinstance(image_data, str):
        try:
            image_bytes = base64.b64decode(image_data)
        except:
            return None
    else:
        image_bytes = image_data
    
    try:
        # Abrir imagen
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convertir a RGB si es necesario (para PNG con transparencia)
        if img.mode in ('RGBA', 'LA', 'P'):
            background = Image.new('RGB', img.size, (255, 255, 255))
            if img.mode == 'P':
                img = img.convert('RGBA')
            if img.mode in ('RGBA', 'LA'):
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            else:
                img = img.convert('RGB')
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Redimensionar manteniendo aspect ratio
        original_width, original_height = img.size
        
        # Calcular ratio de escalado
        ratio_w = max_width / original_width
        ratio_h = max_height / original_height
        ratio = min(ratio_w, ratio_h, 1.0)  # No ampliar, solo reducir
        
        if ratio < 1.0:
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Guardar como WebP
        output = io.BytesIO()
        img.save(output, format='WEBP', quality=quality, optimize=True)
        output.seek(0)
        
        # Retornar base64
        return base64.b64encode(output.read()).decode('utf-8')
        
    except Exception as e:
        print(f"Error procesando imagen: {e}")
        return None


class MemoriaVivaWebsite(http.Controller):
    """Controlador Website para Memoria Viva - Exclusivo Guanarteme"""

    def _get_guanarteme_website(self):
        """Busca y retorna el website de Guanarteme"""
        website = request.env['website'].sudo().search([
            ('domain', 'ilike', 'guanarteme.canariasconectada.es')
        ], limit=1)
        return website

    def _check_guanarteme_website(self):
        """Verifica que estemos en el website de Guanarteme, si no retorna 404"""
        guanarteme = self._get_guanarteme_website()
        if not guanarteme:
            raise werkzeug.exceptions.NotFound()
        return guanarteme

    # ========================================
    # PÁGINA PRINCIPAL - LISTADO
    # ========================================
    @http.route('/memoria-viva', auth='public', website=True)
    def memoria_viva_list(self, **kw):
        """Página principal: Hero + Filtros + Mapa + Galería + Formulario"""
        self._check_guanarteme_website()
        
        # Obtener parámetros de filtro
        search = kw.get('search', '')
        tipo_filter = kw.get('tipo')
        categoria_filter = kw.get('categoria')
        ordenar = kw.get('ordenar', 'default')
        anio_filter = kw.get('anio')
        decada_filter = kw.get('decada')  # Nuevo filtro por década
        
        # Construir dominio base
        Historia = request.env['memoria.viva.historia'].sudo()
        domain = [('state', '=', 'aprobado')]
        
        # Filtro de búsqueda
        if search:
            domain = ['&'] + domain + ['|', ('name', 'ilike', search), ('description', 'ilike', search)]
        
        # Filtro por tipo
        if tipo_filter:
            try:
                tipo_id = int(tipo_filter)
                domain = ['&'] + domain + [('tipo_id', '=', tipo_id)]
            except (ValueError, TypeError):
                pass
        
        # Filtro por categoría
        if categoria_filter:
            try:
                cat_id = int(categoria_filter)
                domain = ['&'] + domain + [('categoria_id', '=', cat_id)]
            except (ValueError, TypeError):
                pass
        
        # Filtro por año (década)
        if anio_filter:
            try:
                anio = int(anio_filter)
                domain = ['&'] + domain + [
                    ('anio_foto', '>=', anio),
                    ('anio_foto', '<', anio + 10)
                ]
            except (ValueError, TypeError):
                pass
        
        # Filtro por década (nuevo)
        if decada_filter:
            try:
                decada = int(decada_filter)
                domain = ['&'] + domain + [
                    ('anio_foto', '>=', decada),
                    ('anio_foto', '<=', decada + 9)
                ]
            except (ValueError, TypeError):
                pass
        
        # Determinar ordenamiento
        order_map = {
            'valoracion': 'rating_avg desc',
            'reacciones': 'like_count desc',
            'likes': 'like_count desc',
            'comentarios': 'comentario_count desc',
            'antiguo': 'anio_foto asc',
            'reciente': 'anio_foto desc',
            'default': 'rating_avg desc'  # Por defecto: mejor valorados primero
        }
        order = order_map.get(ordenar, 'rating_avg desc')
        
        # Paginación
        page = int(kw.get('page', 1))
        limit = int(kw.get('limit', 12))
        
        # Asegurar valores válidos
        if page < 1:
            page = 1
        if limit not in [12, 24, 48]:
            limit = 12
        
        offset = (page - 1) * limit
        
        # Contar total para paginación
        total = Historia.search_count(domain)
        total_pages = (total + limit - 1) // limit  # Redondeo hacia arriba
        
        # Ajustar página si está fuera de rango
        if total_pages > 0 and page > total_pages:
            page = total_pages
            offset = (page - 1) * limit
        
        lugares = Historia.search(domain, order=order, limit=limit, offset=offset)
        
        # Preparar datos JSON para el mapa
        lugares_data = []
        for lugar in lugares:
            if lugar.latitude and lugar.longitude:
                lugares_data.append({
                    'id': lugar.id,
                    'name': lugar.name,
                    'lat': float(lugar.latitude),
                    'lng': float(lugar.longitude),
                    'slug': lugar.slug,
                    'image': f'/web/image/memoria.viva.historia/{lugar.id}/image_main'
                })
        lugares_json = json.dumps(lugares_data)
        
        # Obtener tipos y categorías para filtros (con conteos)
        Tipo = request.env['memoria.viva.tipo'].sudo()
        Categoria = request.env['memoria.viva.categoria'].sudo()
        
        tipos = Tipo.search([('active', '=', True)])
        categorias = Categoria.search([('active', '=', True), ('tipo_id', '=', 11)])  # Solo tipo General
        
        # Preparar tipos y categorías con conteos
        tipos_data = []
        for tipo in tipos:
            count = Historia.search_count([('state', '=', 'aprobado'), ('tipo_id', '=', tipo.id)])
            tipos_data.append({'id': tipo.id, 'name': tipo.name, 'count': count})
        
        categorias_data = []
        for cat in categorias:
            count = Historia.search_count([('state', '=', 'aprobado'), ('categoria_id', '=', cat.id)])
            categorias_data.append({'id': cat.id, 'name': cat.name, 'count': count})
        
        # Parsear filtros a int
        tipo_filter_int = None
        categoria_filter_int = None
        try:
            if tipo_filter:
                tipo_filter_int = int(tipo_filter)
        except:
            pass
        try:
            if categoria_filter:
                categoria_filter_int = int(categoria_filter)
        except:
            pass
        
        # Obtener configuración
        Settings = request.env['memoria.viva.settings'].sudo()
        config = Settings.get_settings()
        
        # Generar lista de décadas para el filtro (1840 hasta año actual)
        from datetime import datetime
        year_now = datetime.now().year
        decadas = list(range(1840, year_now + 1, 10))
        decadas.reverse()  # Más recientes primero
        
        # Calcular conteo de filtros activos
        filtros_activos = 0
        if tipo_filter: filtros_activos += 1
        if categoria_filter: filtros_activos += 1
        if decada_filter: filtros_activos += 1
        if ordenar and ordenar != 'default': filtros_activos += 1
        
        # Obtener session_id para identificar likes del usuario actual
        session_id = request.httprequest.cookies.get('mv_session_id')
        
        # Preparar lista de IDs que ya tienen like de este usuario
        likes_usuario = []
        if session_id:
            Like = request.env['memoria.viva.like'].sudo()
            likes_records = Like.search([('session_id', '=', session_id)])
            likes_usuario = [like.lugar_id.id for like in likes_records]
        
        # Generar URLs para quitar filtros - usar Markup para evitar escaping
        def make_url(exclude=None):
            parts = []
            if search and exclude != 'search':
                parts.append(f'search={search}')
            if tipo_filter and exclude != 'tipo':
                parts.append(f'tipo={tipo_filter}')
            if categoria_filter and exclude != 'categoria':
                parts.append(f'categoria={categoria_filter}')
            if ordenar and ordenar != 'default' and exclude != 'ordenar':
                parts.append(f'ordenar={ordenar}')
            if anio_filter and exclude != 'anio':
                parts.append(f'anio={anio_filter}')
            
            if parts:
                # Usar Markup para que QWeb no escape la URL
                url = '/memoria-viva?' + '&'.join(parts)
                return Markup(url)
            return Markup('/memoria-viva')
        
        url_quitar_search = make_url('search')
        url_quitar_tipo = make_url('tipo')
        url_quitar_categoria = make_url('categoria')
        url_quitar_ordenar = make_url('ordenar')
        url_quitar_anio = make_url('anio')
        
        return request.render('memoria_viva.memoria_viva_list', {
            'lugares': lugares,
            'search': search or '',
            'tipos': tipos_data,
            'categorias': categorias_data,
            'tipo_filter': tipo_filter_int,
            'categoria_filter': categoria_filter_int,
            'ordenar': ordenar,
            'anio_filter': anio_filter,
            'decada_filter': decada_filter,  # Nuevo filtro por década
            'decadas': decadas,
            'lugares_json': lugares_json,
            'config': config,
            'url_quitar_search': url_quitar_search,
            'url_quitar_tipo': url_quitar_tipo,
            'url_quitar_categoria': url_quitar_categoria,
            'url_quitar_ordenar': url_quitar_ordenar,
            'url_quitar_anio': url_quitar_anio,
            'page': page,
            'limit': limit,
            'total': total,
            'total_pages': total_pages,
            'filtros_activos': filtros_activos,  # Conteo de filtros activos
            'likes_usuario': likes_usuario,  # Lista de IDs con like del usuario
        })

    # ========================================
    # PÁGINA DE DETALLE
    # ========================================
    @http.route('/memoria-viva/<string:slug>', auth='public', website=True)
    def memoria_viva_detail(self, slug, **kw):
        """Página de detalle de un lugar"""
        self._check_guanarteme_website()
        
        Historia = request.env['memoria.viva.historia'].sudo()
        lugar = Historia.search([
            ('slug', '=', slug),
            ('state', '=', 'aprobado'),
            '|',
            ('website_primario_id', '=', request.website.id),
            ('website_ids', 'in', [request.website.id])
        ], limit=1)
        
        if not lugar:
            raise werkzeug.exceptions.NotFound()
        
        # Anuncios para sidebar en detalle
        Anuncio = request.env['memoria.viva.anuncio'].sudo()
        anuncios_sidebar = Anuncio.search([
            ('is_visible', '=', True),
            ('position', '=', 'sidebar'),
            ('website_id', '=', request.website.id),
        ], order='sequence', limit=3)
        
        # Obtener configuración
        try:
            Settings = request.env['memoria.viva.settings'].sudo()
            config = Settings.get_settings()
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error("Error obteniendo configuración: %s", str(e))
            config = None
        
        return request.render('memoria_viva.memoria_viva_detail', {
            'lugar': lugar,
            'anuncios_sidebar': anuncios_sidebar,
            'config': config,
        })

    # ========================================
    # API: LISTAR LUGARES (JSON)
    # ========================================
    @http.route('/memoria_viva/api/historias', auth='public', methods=['GET', 'POST'], type='json', csrf=False)
    def api_list(self, **kw):
        """API JSON para listar lugares aprobados"""
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
        except:
            data = {}
        
        # Verificar website
        guanarteme = self._get_guanarteme_website()
        if not guanarteme:
            return {'success': False, 'error': 'Website no configurado'}
        
        Historia = request.env['memoria.viva.historia'].sudo()
        domain = [
            ('state', '=', 'aprobado'),
            '|',
            ('website_primario_id', '=', guanarteme.id),
            ('website_ids', 'in', [guanarteme.id])
        ]
        
        # Filtros
        search = data.get('search', '')
        if search:
            domain += ['|', ('name', 'ilike', search), ('description', 'ilike', search)]
        
        limit = min(int(data.get('limit', 20)), 100)
        offset = int(data.get('offset', 0))
        
        total = Historia.search_count(domain)
        lugares = Historia.search(domain, limit=limit, offset=offset, order='create_date desc')
        
        items = []
        for lugar in lugares:
            items.append({
                'id': lugar.id,
                'name': lugar.name,
                'description': lugar.description or '',
                'slug': lugar.slug,
                'image_main': f'/web/image/memoria.viva.historia/{lugar.id}/image_main',
                'latitude': lugar.latitude,
                'longitude': lugar.longitude,
                'tipo': lugar.tipo_id.name if lugar.tipo_id else '',
                'categoria': lugar.categoria_id.name if lugar.categoria_id else '',
                'create_date': lugar.create_date.isoformat() if lugar.create_date else '',
            })
        
        return {
            'success': True,
            'data': {
                'total': total,
                'items': items,
            }
        }

    # ========================================
    # API: ENVIAR LUGAR (JSON)
    # ========================================
    @http.route('/memoria_viva/api/submit', auth='public', methods=['POST'], type='json', csrf=False)
    def api_submit(self, **kw):
        """API JSON para enviar un nuevo lugar con registro de usuario"""
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
        except Exception as e:
            return {'success': False, 'error': f'Datos JSON inválidos: {str(e)}'}
        
        # Verificar website
        guanarteme = self._get_guanarteme_website()
        if not guanarteme:
            return {'success': False, 'error': 'Website no disponible'}
        
        # Anti-spam: Validar honeypot
        if data.get('website'):
            return {'success': False, 'error': 'Spam detectado'}
        
        # Validaciones básicas
        if not data.get('name'):
            return {'success': False, 'error': 'El nombre del lugar es requerido'}
        
        if not data.get('image_main'):
            return {'success': False, 'error': 'La imagen es requerida'}
        
        # Validar categoría obligatoria
        if not data.get('categoria_id'):
            return {'success': False, 'error': 'La categoría es obligatoria'}
        
        # Validar teléfono obligatorio para usuarios no logueados (registro)
        if request.env.user._is_public() and data.get('modo_auth') != 'login':
            telefono = data.get('publicador_telefono', '').strip()
            if not telefono or len(telefono) < 5:
                return {'success': False, 'error': 'El teléfono es obligatorio (mínimo 5 dígitos)'}
        
        # Inicializar DNI
        dni = data.get('dni_remitente', '').strip()
        
        # Nota: La validación del DNI se hace más abajo según el modo (login vs registro)
        
        try:
            # Validar año de foto
            anio_foto = data.get('anio_foto')
            if not anio_foto:
                return {'success': False, 'error': 'El año de la fotografía es requerido'}
            try:
                anio_foto = int(anio_foto)
                year_now = datetime.now().year
                if anio_foto < 1840 or anio_foto > year_now:
                    return {'success': False, 'error': f'El año debe estar entre 1840 y {year_now}'}
            except (ValueError, TypeError):
                return {'success': False, 'error': 'El año debe ser un número válido'}
            
            # ========================================
            # FASE 2: MANEJO DE USUARIO
            # ========================================
            partner_id = None
            user_created = False
            
            # Si usuario está logueado, usar su partner
            if not request.env.user._is_public():
                partner_id = request.env.user.partner_id.id
                # Usar DNI del partner si no se proporcionó
                if not dni and request.env.user.partner_id.dni:
                    dni = request.env.user.partner_id.dni
            else:
                # Usuario anónimo - detectar modo de autenticación
                modo_auth = data.get('modo_auth', 'registro')
                
                if modo_auth == 'login':
                    # ========================================
                    # MODO LOGIN: Validar credenciales
                    # ========================================
                    login_email = data.get('login_email', '').strip()
                    login_password = data.get('login_password', '').strip()
                    
                    if not login_email or not login_password:
                        return {'success': False, 'error': 'Email y contraseña son requeridos'}
                    
                    # Intentar autenticar
                    try:
                        credential = {'login': login_email, 'password': login_password, 'type': 'password'}
                        auth_result = request.session.authenticate(request.env, credential)
                        
                        if auth_result:
                            # Autenticación exitosa
                            partner_id = request.env.user.partner_id.id
                            # Usar DNI del partner si no se proporcionó
                            if not dni and request.env.user.partner_id.dni:
                                dni = request.env.user.partner_id.dni
                        else:
                            return {'success': False, 'error': 'Credenciales inválidas'}
                    except Exception as e:
                        return {'success': False, 'error': 'Email o contraseña incorrectos'}
                
                else:
                    # ========================================
                    # MODO REGISTRO: Crear nuevo usuario
                    # ========================================
                    
                    # Validar DNI (5-20 caracteres) - Solo para registro
                    if not dni or len(dni) < 5 or len(dni) > 20:
                        return {'success': False, 'error': 'El documento debe tener entre 5 y 20 caracteres'}
                    
                    password = data.get('password', '').strip()
                    if not password or len(password) < 6:
                        return {'success': False, 'error': 'La contraseña es requerida (mínimo 6 caracteres)'}
                    
                    email = data.get('publicador_email', '').strip()
                    if not email:
                        return {'success': False, 'error': 'El email es requerido'}
                    
                    # Verificar si el email ya existe
                    existing_user = request.env['res.users'].sudo().search([('login', '=', email)], limit=1)
                    if existing_user:
                        return {
                            'success': False, 
                            'error': 'Este email ya está registrado. Por favor inicia sesión con tu cuenta o usa otro email diferente.'
                        }
                    
                    # Buscar compañía Zona Comercial Guanarteme
                    Company = request.env['res.company'].sudo()
                    company = Company.search([('name', 'ilike', 'Zona Comercial Guanarteme')], limit=1)
                    company_id = company.id if company else request.env.ref('base.main_company').id
                    
                    # Crear partner
                    Partner = request.env['res.partner'].sudo()
                    partner = Partner.create({
                        'name': data.get('publicador_nombre', 'Usuario'),
                        'email': email,
                        'phone': data.get('publicador_telefono', ''),
                        'dni': dni,
                        'company_id': company_id,
                        'is_memoria_viva_user': True,
                    })
                    partner_id = partner.id
                    
                    # Crear usuario portal
                    Users = request.env['res.users'].sudo()
                    user = Users.create({
                        'name': partner.name,
                        'login': email,
                        'email': email,
                        'password': password,
                        'partner_id': partner.id,
                        'company_id': company_id,
                        'company_ids': [(4, company_id)],
                        'group_ids': [(6, 0, [request.env.ref('base.group_portal').id])],
                    })
                    user_created = True
                    
                    # Autenticar automáticamente
                    credential = {'login': email, 'password': password, 'type': 'password'}
                    request.session.authenticate(request.env, credential)
            
            # ========================================
            # PREPARAR VALORES DEL LUGAR
            # ========================================
            vals = {
                'name': data['name'],
                'description': data.get('description', ''),
                'descripcion_larga': data.get('descripcion_larga', ''),
                'anio_foto': anio_foto,
                'website_primario_id': guanarteme.id,
                'state': 'pendiente',
                'partner_id': partner_id,  # Quién envió el lugar
                'publicador_nombre': data.get('publicador_nombre', 'Anónimo'),
                'publicador_telefono': data.get('publicador_telefono', ''),
                'publicador_email': data.get('publicador_email', ''),
                'dni_remitente': dni,
            }
            
            # Coordenadas (opcionales)
            if data.get('latitude'):
                vals['latitude'] = float(data['latitude'])
            if data.get('longitude'):
                vals['longitude'] = float(data['longitude'])
            if data.get('direccion'):
                vals['direccion'] = data['direccion']
            
            # Tipo y categoría
            if data.get('tipo_id'):
                vals['tipo_id'] = int(data['tipo_id'])
            if data.get('categoria_id'):
                vals['categoria_id'] = int(data['categoria_id'])
            
            # Imagen (base64)
            image_data = data['image_main']
            if image_data.startswith('data:image'):
                image_data = image_data.split(',')[1]
            vals['image_main'] = image_data
            
            # Crear lugar
            Historia = request.env['memoria.viva.historia'].sudo()
            lugar = Historia.create(vals)
            
            # Preparar respuesta
            result = {
                'success': True,
                'id': lugar.id,
                'reload': True,
            }
            
            if user_created:
                result['message'] = '¡Registro exitoso! Tu lugar ha sido enviado y está pendiente de aprobación.'
                result['user_created'] = True
            else:
                result['message'] = 'Tu lugar ha sido enviado correctamente y está pendiente de aprobación.'
            
            return result
            
        except Exception as e:
            return {'success': False, 'error': str(e)}

    # ========================================
    # CLICK EN ANUNCIO (TRACKING)
    # ========================================
    @http.route('/memoria-viva/anuncio/click/<int:anuncio_id>', auth='public', type='http')
    def anuncio_click(self, anuncio_id, **kw):
        """Registra un clic en el anuncio y redirige"""
        Anuncio = request.env['memoria.viva.anuncio'].sudo()
        anuncio = Anuncio.browse(anuncio_id)
        
        if anuncio.exists() and anuncio.is_visible:
            anuncio.increment_click()
            if anuncio.url:
                return werkzeug.utils.redirect(anuncio.url)
        
        return werkzeug.utils.redirect('/memoria-viva')

    # ========================================
    # LIKE A LUGAR
    # ========================================
    @http.route('/memoria-viva/like/<int:lugar_id>', auth='public', type='http', csrf=False)
    def like_lugar(self, lugar_id, **kw):
        """Registra un like a un lugar. Retorna el nuevo conteo."""
        import json
        headers = {'Content-Type': 'application/json'}
        
        try:
            Lugar = request.env['memoria.viva.historia'].sudo()
            Like = request.env['memoria.viva.like'].sudo()
            Settings = request.env['memoria.viva.settings'].sudo().get_settings()
            
            lugar = Lugar.browse(lugar_id)
            if not lugar.exists() or lugar.state != 'aprobado':
                return request.make_response(json.dumps({'success': False, 'error': 'Lugar no encontrado'}), headers=headers)
            
            # Obtener session_id de la cookie o crear uno nuevo
            session_id = request.httprequest.cookies.get('mv_session_id')
            if not session_id:
                import uuid
                session_id = str(uuid.uuid4())
            
            # Verificar si ya dio like
            existing = Like.search([('lugar_id', '=', lugar_id), ('session_id', '=', session_id)], limit=1)
            if existing:
                response = request.make_response(json.dumps({
                    'success': False, 
                    'error': 'Ya has dado like a este lugar', 
                    'already_liked': True,
                    'like_count': lugar.like_count
                }), headers=headers)
                response.set_cookie('mv_session_id', session_id, max_age=60*60*24*Settings.likes_cookie_days)
                return response
            
            # Crear like
            Like.create({
                'lugar_id': lugar_id,
                'session_id': session_id,
                'ip_address': request.httprequest.remote_addr,
            })
            
            # Invalidar cache y recalcular
            lugar.invalidate_recordset()
            like_count = Like.search_count([('lugar_id', '=', lugar_id)])
            lugar.like_count = like_count
            
            response = request.make_response(json.dumps({
                'success': True,
                'like_count': like_count,
                'session_id': session_id,
            }), headers=headers)
            
            # Establecer cookie con duración configurada
            response.set_cookie('mv_session_id', session_id, max_age=60*60*24*Settings.likes_cookie_days)
            return response
            
        except Exception as e:
            return request.make_response(json.dumps({'success': False, 'error': str(e)}), headers=headers)

    # ========================================
    # COMENTARIOS
    # ========================================
    @http.route('/memoria-viva/comentario/enviar', auth='user', type='http', csrf=False, methods=['POST'])
    def enviar_comentario(self, **kw):
        """Endpoint para enviar un comentario. Requiere login."""
        import json
        headers = {'Content-Type': 'application/json'}
        
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
            
            lugar_id = data.get('lugar_id')
            contenido = data.get('contenido', '').strip()
            parent_id = data.get('parent_id') or None
            
            if not lugar_id:
                return request.make_response(json.dumps({'success': False, 'error': 'Lugar no especificado'}), headers=headers)
            
            if not contenido:
                return request.make_response(json.dumps({'success': False, 'error': 'El comentario está vacío'}), headers=headers)
            
            # Verificar que el lugar existe y está aprobado
            Lugar = request.env['memoria.viva.historia'].sudo()
            lugar = Lugar.browse(int(lugar_id))
            if not lugar.exists() or lugar.state != 'aprobado':
                return request.make_response(json.dumps({'success': False, 'error': 'Lugar no encontrado'}), headers=headers)
            
            # Verificar configuración de comentarios
            Settings = request.env['memoria.viva.settings'].sudo().get_settings()
            if not Settings.permitir_comentarios:
                return request.make_response(json.dumps({'success': False, 'error': 'Los comentarios están deshabilitados'}), headers=headers)
            
            # Crear comentario
            Comentario = request.env['memoria.viva.comentario'].sudo()
            vals = {
                'lugar_id': int(lugar_id),
                'autor_id': request.env.user.id,
                'contenido': contenido,
            }
            if parent_id:
                vals['parent_id'] = int(parent_id)
            
            comentario = Comentario.create(vals)
            
            # Preparar respuesta
            result = {
                'success': True,
                'comentario': {
                    'id': comentario.id,
                    'autor_nombre': comentario.autor_nombre,
                    'autor_imagen': comentario.autor_imagen.decode() if comentario.autor_imagen else None,
                    'contenido': comentario.contenido,
                    'fecha': comentario.create_date.strftime('%d/%m/%Y %H:%M'),
                    'estado': comentario.estado,
                    'pendiente_moderacion': comentario.contiene_palabras_prohibidas,
                }
            }
            
            if comentario.contiene_palabras_prohibidas:
                result['mensaje'] = 'Tu comentario está pendiente de moderación y será revisado por un administrador.'
            
            return request.make_response(json.dumps(result), headers=headers)
            
        except Exception as e:
            return request.make_response(json.dumps({'success': False, 'error': str(e)}), headers=headers)
    
    @http.route('/memoria-viva/comentario/listar', auth='public', type='http', methods=['GET'])
    def listar_comentarios(self, lugar_id, offset=0, limit=10, **kw):
        """Endpoint para listar comentarios aprobados de un lugar.
        
        Si comentarios_publicos está desactivado en configuración, requiere login.
        """
        import json
        headers = {'Content-Type': 'application/json'}
        
        try:
            if not lugar_id:
                return request.make_response(json.dumps({'success': False, 'error': 'Lugar no especificado'}), headers=headers)
            
            # Verificar configuración de visibilidad pública
            Config = request.env['memoria.viva.settings'].sudo().get_settings()
            if not Config.comentarios_publicos:
                # Si no es público, requerir usuario logueado
                if not request.env.user or request.env.user._is_public():
                    return request.make_response(json.dumps({
                        'success': False, 
                        'error': 'Debes iniciar sesión para ver los comentarios',
                        'requiere_login': True
                    }), headers=headers)
            
            Comentario = request.env['memoria.viva.comentario'].sudo()
            comentarios = Comentario.get_comentarios_aprobados(
                int(lugar_id),
                offset=int(offset),
                limit=int(limit)
            )
            
            # Contar total de comentarios aprobados
            total = Comentario.search_count([
                ('lugar_id', '=', int(lugar_id)),
                ('estado', '=', 'aprobado'),
                ('parent_id', '=', False)
            ])
            
            return request.make_response(json.dumps({
                'success': True,
                'comentarios': comentarios,
                'total': total,
                'tiene_mas': total > (int(offset) + int(limit))
            }), headers=headers)
            
        except Exception as e:
            return request.make_response(json.dumps({'success': False, 'error': str(e)}), headers=headers)

    # ========================================
    # VALORACIONES (RATINGS)
    # ========================================
    @http.route('/memoria-viva/rating/enviar', auth='user', type='http', csrf=False, methods=['POST'])
    def enviar_rating(self, **kw):
        """Endpoint para enviar una valoración. Requiere login."""
        import json
        headers = {'Content-Type': 'application/json'}
        
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
            
            lugar_id = data.get('lugar_id')
            rating = data.get('rating')
            
            if not lugar_id:
                return request.make_response(json.dumps({
                    'success': False, 
                    'error': 'Lugar no especificado'
                }), headers=headers)
            
            if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
                return request.make_response(json.dumps({
                    'success': False, 
                    'error': 'La valoración debe ser un número entre 1 y 5'
                }), headers=headers)
            
            # Verificar que el lugar existe y está aprobado
            Lugar = request.env['memoria.viva.historia'].sudo()
            lugar = Lugar.browse(int(lugar_id))
            if not lugar.exists() or lugar.state != 'aprobado':
                return request.make_response(json.dumps({
                    'success': False, 
                    'error': 'Lugar no encontrado'
                }), headers=headers)
            
            # Crear o actualizar rating
            Rating = request.env['memoria.viva.rating'].sudo()
            
            # Buscar si ya existe un rating de este usuario para este lugar
            existing_rating = Rating.search([
                ('lugar_id', '=', int(lugar_id)),
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            
            if existing_rating:
                # Actualizar rating existente
                existing_rating.write({'rating': rating})
                mensaje = 'Tu valoración ha sido actualizada.'
            else:
                # Crear nuevo rating
                Rating.create({
                    'lugar_id': int(lugar_id),
                    'user_id': request.env.user.id,
                    'rating': rating
                })
                mensaje = '¡Gracias por valorar este lugar!'
            
            # Recalcular promedio
            lugar.invalidate_recordset()
            
            return request.make_response(json.dumps({
                'success': True,
                'mensaje': mensaje,
                'rating_avg': lugar.rating_avg,
                'rating_count': lugar.rating_count,
                'user_rating': rating
            }), headers=headers)
            
        except Exception as e:
            return request.make_response(json.dumps({
                'success': False, 
                'error': str(e)
            }), headers=headers)
    
    @http.route('/memoria-viva/rating/eliminar', auth='user', type='http', csrf=False, methods=['POST'])
    def eliminar_rating(self, **kw):
        """Endpoint para eliminar la valoración del usuario. Requiere login."""
        import json
        headers = {'Content-Type': 'application/json'}
        
        try:
            data = json.loads(request.httprequest.data) if request.httprequest.data else {}
            lugar_id = data.get('lugar_id')
            
            if not lugar_id:
                return request.make_response(json.dumps({
                    'success': False, 
                    'error': 'Lugar no especificado'
                }), headers=headers)
            
            # Buscar y eliminar el rating del usuario
            Rating = request.env['memoria.viva.rating'].sudo()
            existing_rating = Rating.search([
                ('lugar_id', '=', int(lugar_id)),
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            
            if existing_rating:
                existing_rating.unlink()
                
                # Recalcular promedio
                Lugar = request.env['memoria.viva.historia'].sudo()
                lugar = Lugar.browse(int(lugar_id))
                lugar.invalidate_recordset()
                
                return request.make_response(json.dumps({
                    'success': True,
                    'mensaje': 'Tu valoración ha sido eliminada.',
                    'rating_avg': lugar.rating_avg,
                    'rating_count': lugar.rating_count,
                    'user_rating': 0
                }), headers=headers)
            else:
                return request.make_response(json.dumps({
                    'success': False, 
                    'error': 'No tienes una valoración para este lugar'
                }), headers=headers)
                
        except Exception as e:
            return request.make_response(json.dumps({
                'success': False, 
                'error': str(e)
            }), headers=headers)
    
    @http.route('/memoria-viva/rating/mi-valoracion', auth='user', type='http', methods=['GET'])
    def mi_valoracion(self, lugar_id, **kw):
        """Endpoint para obtener la valoración del usuario actual. Requiere login."""
        import json
        headers = {'Content-Type': 'application/json'}
        
        try:
            if not lugar_id:
                return request.make_response(json.dumps({
                    'success': False, 
                    'error': 'Lugar no especificado'
                }), headers=headers)
            
            Rating = request.env['memoria.viva.rating'].sudo()
            rating = Rating.search([
                ('lugar_id', '=', int(lugar_id)),
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            
            return request.make_response(json.dumps({
                'success': True,
                'rating': rating.rating if rating else 0
            }), headers=headers)
            
        except Exception as e:
            return request.make_response(json.dumps({
                'success': False, 
                'error': str(e)
            }), headers=headers)


    # ========================================
