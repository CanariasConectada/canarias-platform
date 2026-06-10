# -*- coding: utf-8 -*-
import base64
import io
import re
import unicodedata
import logging
from PIL import Image

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

# Límites actualizados
MAX_SIZE_KB = 2048  # 2MB máximo
MAX_SIZE_BYTES = MAX_SIZE_KB * 1024
ALLOWED_FORMATS = {'JPEG', 'JPG', 'PNG', 'WEBP', 'GIF', 'BMP', 'TIFF'}

# Dimensiones para diferentes usos
GRID_MAX_WIDTH = 600
GRID_MAX_HEIGHT = 600
GRID_QUALITY = 85

DETAIL_MAX_WIDTH = 1600
DETAIL_MAX_HEIGHT = 1200
DETAIL_QUALITY = 90


def _webp_supported():
    """Verifica si WebP está soportado por Pillow"""
    try:
        from PIL import features
        return features.check('webp') and 'WEBP' in Image.SAVE
    except Exception:
        return False

# Cache del soporte WebP
_WEBP_SUPPORTED = None

def _procesar_imagen_webp(image_data, max_width=1600, max_height=1200, quality=90):
    """
    Procesa imagen: convierte a WebP (o JPEG como fallback) con redimensionamiento proporcional.
    """
    global _WEBP_SUPPORTED
    if _WEBP_SUPPORTED is None:
        _WEBP_SUPPORTED = _webp_supported()
    
    if not image_data:
        return None
        
    # Decodificar base64 - manejar tanto str como bytes (Odoo store bytes con base64)
    try:
        if isinstance(image_data, str):
            image_bytes = base64.b64decode(image_data)
        elif isinstance(image_data, bytes):
            # Odoo almacena bytes del string base64, no los bytes binarios
            image_str = image_data.decode('utf-8')
            image_bytes = base64.b64decode(image_str)
        else:
            image_bytes = image_data
    except Exception as e:
        _logger.error(f"Error decodificando base64: {e}")
        return None
    
    try:
        # Abrir imagen
        img = Image.open(io.BytesIO(image_bytes))
        
        # Convertir a RGB si es necesario
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
        ratio_w = max_width / original_width
        ratio_h = max_height / original_height
        ratio = min(ratio_w, ratio_h, 1.0)  # No ampliar, solo reducir
        
        new_width, new_height = original_width, original_height
        if ratio < 1.0:
            new_width = int(original_width * ratio)
            new_height = int(original_height * ratio)
            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        
        # Guardar como WebP o JPEG según disponibilidad
        output = io.BytesIO()
        if _WEBP_SUPPORTED:
            img.save(output, format='WEBP', quality=quality, optimize=True)
            _logger.debug(f"Imagen guardada como WebP ({new_width}x{new_height})")
        else:
            # Fallback a JPEG optimizado
            img.save(output, format='JPEG', quality=quality, optimize=True, progressive=True)
            _logger.debug(f"Imagen guardada como JPEG ({new_width}x{new_height})")
        output.seek(0)
        
        return base64.b64encode(output.read()).decode('utf-8')
        
    except Exception as e:
        _logger.error(f"Error procesando imagen: {e}")
        return None


def _slugify(value):
    value = unicodedata.normalize('NFKD', str(value)).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[-\s]+', '-', value)


def _generate_unique_slug(env, name, website_primario_id):
    """Generar un slug único, agregando número incremental si existe"""
    base_slug = _slugify(name)
    slug = base_slug
    counter = 1
    
    # Verificar si el slug base existe
    while env['lugares.interes.historia'].sudo().search([
        ('slug', '=', slug),
        ('website_primario_id', '=', website_primario_id)
    ], limit=1):
        slug = f"{base_slug}-{counter}"
        counter += 1
        # Evitar bucle infinito (límite de 1000 intentos)
        if counter > 1000:
            # Usar timestamp como fallback
            import time
            slug = f"{base_slug}-{int(time.time())}"
            break
    
    return slug


def _validate_image(value, field_name='Imagen'):
    if not value:
        return
    try:
        data = base64.b64decode(value)
    except Exception:
        raise ValidationError(_("%s: el archivo no es una imagen válida en base64.", field_name))

    if len(data) > MAX_SIZE_BYTES:
        raise ValidationError(_("%s excede el peso máximo permitido de %s KB.", field_name, MAX_SIZE_KB))

    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
    except Exception:
        raise ValidationError(_("%s: el archivo no es una imagen válida.", field_name))

    img = Image.open(io.BytesIO(data))
    width, height = img.size
    img_format = (img.format or '').upper()
    if img_format == 'JPEG':
        img_format = 'JPG'

    if img_format not in ALLOWED_FORMATS:
        raise ValidationError(_("%s: formato no permitido. Use JPG, PNG o WEBP.", field_name))


class LugaresInteresHistoria(models.Model):
    _name = 'lugares.interes.historia'
    _description = 'Lugar de Interés'
    _order = 'create_date desc'
    _rec_name = 'name'

    # ========================================
    # 1. IDENTIFICACIÓN Y CLASIFICACIÓN
    # ========================================
    name = fields.Char(string='Nombre/Título', required=True, index=True)
    slug = fields.Char(string='Slug URL', required=True, index=True)
    
    # Jerarquía de categorías (3 niveles)
    tipo_id = fields.Many2one('lugares.interes.tipo', string='Tipo', ondelete='restrict')
    categoria_id = fields.Many2one('lugares.interes.categoria', string='Categoría', ondelete='restrict')
    subcategoria_id = fields.Many2one('lugares.interes.subcategoria', string='Subcategoría', ondelete='restrict')
    
    # ========================================
    # 2. UBICACIÓN
    # ========================================
    ciudad = fields.Char(string='Ciudad')
    barrio = fields.Char(string='Barrio')
    direccion = fields.Char(string='Dirección completa')
    
    latitude = fields.Float(string='Latitud', digits=(10, 8))
    longitude = fields.Float(string='Longitud', digits=(11, 8))
    
    # ========================================
    # 3. CONTACTO Y REDES
    # ========================================
    telefono = fields.Char(string='Teléfono')
    whatsapp = fields.Char(string='WhatsApp')
    instagram = fields.Char(string='Instagram')
    tiktok = fields.Char(string='TikTok')
    website_url = fields.Char(string='Web')
    
    # ========================================
    # 4. DESCRIPCIONES
    # ========================================
    description = fields.Text(string='Descripción corta')
    descripcion_larga = fields.Html(string='Descripción larga')
    
    # ========================================
    # 5. HORARIO
    # ========================================
    horario = fields.Char(string='Horario')
    
    # ========================================
    # 6. FOTOS
    # ========================================
    image_main = fields.Image(string='Imagen destacada', required=True, attachment=True)
    image_main_grid = fields.Image(string='Imagen Grid (WebP)', attachment=True, 
                                   help='Versión optimizada para grid: 600x600px máx, WebP')
    image_main_detail = fields.Image(string='Imagen Detail (WebP)', attachment=True,
                                     help='Versión optimizada para detalle: 1600x1200px máx, WebP')
    
    # Campos calculados para URLs de imágenes (evitan problema con /web/image)
    image_grid_url = fields.Char(string='URL Grid', compute='_compute_image_urls', store=False)
    image_detail_url = fields.Char(string='URL Detail', compute='_compute_image_urls', store=False)
    
    image_ids = fields.One2many('lugares.interes.historia.image', 'historia_id', string='Fotografías adicionales')
    
    tags_busqueda = fields.Char(string='Tags de búsqueda')
    
    # ========================================
    # 7. EXPERIENCIA Y PÚBLICO (Tags Many2many)
    # ========================================
    publico_ids = fields.Many2many('lugares.interes.publico.objetivo', string='Público objetivo')
    momento_ids = fields.Many2many('lugares.interes.momento.dia', string='Momento del día')
    ambiente_ids = fields.Many2many('lugares.interes.ambiente', string='Ambiente')
    experiencia_ids = fields.Many2many('lugares.interes.experiencia', string='Experiencias')
    
    # ========================================
    # RELACIONES Y ESTADO
    # ========================================
    # Microsites (jerarquía padre/hijo)
    website_primario_id = fields.Many2one('website', string='Microsite primario', ondelete='restrict')
    website_ids = fields.Many2many('website', string='Microsites')
    
    # Datos del publicador (campos simples, no contacto)
    publicador_nombre = fields.Char(string='Publicado por (nombre)')
    publicador_telefono = fields.Char(string='Teléfono contacto')
    publicador_email = fields.Char(string='Email contacto')
    
    # Usuario que envió el lugar (vinculación a res.partner)
    partner_id = fields.Many2one(
        'res.partner',
        string='Usuario que envió',
        readonly=True,
        help='Usuario registrado que envió este lugar'
    )
    
    # Campo DNI simple (5-20 caracteres)
    # Nota: La validación de required se hace en el controlador (anónimos vs logueados)
    dni_remitente = fields.Char(
        string='Documento de identidad',
        help='DNI/NIE del remitente. Para usuarios registrados, se obtiene de su perfil si no se especifica.',
    )
    user_id = fields.Many2one('res.users', string='Aprobado/Gestionado por', ondelete='set null')
    
    state = fields.Selection([
        ('borrador', 'Borrador'),
        ('pendiente', 'Pendiente de aprobación'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado'),
    ], string='Estado', default='borrador', required=True)
    
    active = fields.Boolean(string='Activo', default=True)

    # ========================================
    # CAMPOS COMPUTADOS (Likes, Ratings, Comentarios)
    # ========================================
    like_count = fields.Integer(
        string='Nº de Likes',
        compute='_compute_like_count',
        store=True
    )
    
    rating_avg = fields.Float(
        string='Valoración media',
        compute='_compute_rating_stats',
        store=True,
        digits=(2, 1)
    )
    
    rating_count = fields.Integer(
        string='Nº de valoraciones',
        compute='_compute_rating_stats',
        store=True
    )
    
    comentario_count = fields.Integer(
        string='Nº de comentarios',
        compute='_compute_comentario_count',
        store=True
    )

    # ========================================
    # CONSTRAINTS
    # ========================================
    _unique_slug_website = models.Constraint(
        'unique(slug, website_primario_id)',
        'El slug debe ser único dentro del mismo microsite.',
    )

    # ========================================
    # VALIDACIONES
    # ========================================
    @api.constrains('slug', 'website_primario_id')
    def _check_slug_unique(self):
        """Validar que el slug sea único dentro del mismo microsite"""
        for record in self:
            if record.slug:
                domain = [
                    ('slug', '=', record.slug),
                    ('website_primario_id', '=', record.website_primario_id.id if record.website_primario_id else False),
                    ('id', '!=', record.id)
                ]
                if self.search_count(domain) > 0:
                    raise ValidationError(_("El slug '%s' ya existe en este microsite.", record.slug))

    @api.constrains('latitude', 'longitude')
    def _check_coordinates(self):
        for record in self:
            if record.latitude and (record.latitude < -90 or record.latitude > 90):
                raise ValidationError(_("La latitud debe estar entre -90 y 90."))
            if record.longitude and (record.longitude < -180 or record.longitude > 180):
                raise ValidationError(_("La longitud debe estar entre -180 y 180."))

    @api.constrains('dni_remitente')
    def _check_dni_length(self):
        """Validar longitud 5-20 caracteres"""
        for record in self:
            if record.dni_remitente:
                if len(record.dni_remitente) < 5 or len(record.dni_remitente) > 20:
                    raise ValidationError(_('El documento debe tener entre 5 y 20 caracteres.'))

    @api.constrains('categoria_id')
    def _check_categoria_required(self):
        """Validar que categoría esté seleccionada"""
        for record in self:
            if not record.categoria_id:
                raise ValidationError(_('La categoría es obligatoria.'))

    # ========================================
    # MÉTODOS OVERRIDE
    # ========================================
    def _procesar_imagen_principal(self, vals):
        """Procesa image_main y genera versiones WebP optimizadas"""
        if not vals.get('image_main'):
            return vals
        
        image_main = vals.get('image_main')
        
        # Validar tamaño (2MB máximo)
        try:
            image_bytes = base64.b64decode(image_main) if isinstance(image_main, str) else image_main
            if len(image_bytes) > MAX_SIZE_BYTES:
                raise ValidationError(_("La imagen excede el peso máximo permitido de %s KB.", MAX_SIZE_KB))
        except Exception as e:
            if 'excede' in str(e):
                raise
            _logger.warning(f"No se pudo validar tamaño de imagen: {e}")
        
        # Generar versión GRID (600x600 max)
        image_grid = _procesar_imagen_webp(image_main, GRID_MAX_WIDTH, GRID_MAX_HEIGHT, GRID_QUALITY)
        if image_grid:
            vals['image_main_grid'] = image_grid
            _logger.info("Imagen GRID generada correctamente")
        
        # Generar versión DETAIL (1600x1200 max)
        image_detail = _procesar_imagen_webp(image_main, DETAIL_MAX_WIDTH, DETAIL_MAX_HEIGHT, DETAIL_QUALITY)
        if image_detail:
            vals['image_main_detail'] = image_detail
            _logger.info("Imagen DETAIL generada correctamente")
        
        return vals

    def _hacer_imagenes_publicas(self):
        """Hace públicos los attachments de las imágenes para acceso web"""
        Attachment = self.env['ir.attachment']
        for record in self:
            attachments = Attachment.search([
                ('res_model', '=', 'lugares.interes.historia'),
                ('res_id', '=', record.id),
                ('res_field', 'in', ['image_main', 'image_main_grid', 'image_main_detail']),
                ('public', '=', False)
            ])
            if attachments:
                attachments.write({'public': True})
                _logger.info(f"Hechos públicos {len(attachments)} attachments para {record.name}")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Procesar imagen y generar versiones WebP
            vals = self._procesar_imagen_principal(vals)
            
            if not vals.get('slug') and vals.get('name'):
                website_id = vals.get('website_primario_id')
                vals['slug'] = _generate_unique_slug(self.env, vals['name'], website_id)
            # Sincronizar website_primario_id con website_ids
            if vals.get('website_primario_id') and not vals.get('website_ids'):
                vals['website_ids'] = [(4, vals['website_primario_id'])]
        
        records = super(LugaresInteresHistoria, self).create(vals_list)
        # Hacer imágenes públicas después de crear
        records._hacer_imagenes_publicas()
        return records

    def write(self, vals):
        # Procesar imagen si se actualiza
        if vals.get('image_main'):
            vals = self._procesar_imagen_principal(vals)
        
        # NOTA: Ya no regeneramos slug automáticamente al cambiar nombre
        # El usuario puede editar el slug manualmente, y se valida unicidad en el constraint
        
        # Sincronizar website_primario_id con website_ids
        if 'website_primario_id' in vals:
            vals['website_ids'] = [(4, vals['website_primario_id'])]
        
        result = super(LugaresInteresHistoria, self).write(vals)
        # Hacer imágenes públicas después de actualizar si cambió la imagen
        if vals.get('image_main') or vals.get('image_main_grid') or vals.get('image_main_detail'):
            self._hacer_imagenes_publicas()
        return result

    # ========================================
    # MÉTODOS COMPUTADOS PARA URLs DE IMÁGENES
    # ========================================
    @api.depends('image_main_grid', 'image_main_detail')
    def _compute_image_urls(self):
        """Calcula las URLs directas a los attachments de imágenes"""
        Attachment = self.env['ir.attachment']
        for record in self:
            # URL para grid
            if record.image_main_grid:
                att_grid = Attachment.search([
                    ('res_model', '=', 'lugares.interes.historia'),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'image_main_grid')
                ], limit=1)
                record.image_grid_url = f'/web/content/{att_grid.id}' if att_grid else False
            else:
                record.image_grid_url = False
            
            # URL para detail
            if record.image_main_detail:
                att_detail = Attachment.search([
                    ('res_model', '=', 'lugares.interes.historia'),
                    ('res_id', '=', record.id),
                    ('res_field', '=', 'image_main_detail')
                ], limit=1)
                record.image_detail_url = f'/web/content/{att_detail.id}' if att_detail else False
            else:
                record.image_detail_url = False

    # ========================================
    # MÉTODOS COMPUTADOS
    # ========================================
    @api.depends('active')
    def _compute_like_count(self):
        """Contar likes de este lugar"""
        for record in self:
            record.like_count = self.env['lugares.interes.like'].search_count([
                ('lugar_id', '=', record.id)
            ])
    
    @api.depends('active')
    def _compute_rating_stats(self):
        """Calcular promedio y cantidad de valoraciones"""
        for record in self:
            ratings = self.env['lugares.interes.rating'].search([
                ('lugar_id', '=', record.id)
            ])
            if ratings:
                record.rating_count = len(ratings)
                record.rating_avg = sum(r.rating for r in ratings) / len(ratings)
            else:
                record.rating_count = 0
                record.rating_avg = 0.0
    
    @api.depends('active')
    def _compute_comentario_count(self):
        """Contar comentarios aprobados de este lugar"""
        for record in self:
            record.comentario_count = self.env['lugares.interes.comentario'].search_count([
                ('lugar_id', '=', record.id),
                ('estado', '=', 'aprobado')
            ])

    # ========================================
    # MÉTODOS PARA URLs DE IMÁGENES
    # ========================================
    def get_image_grid_url(self):
        """Devuelve la URL directa al attachment de image_main_grid"""
        self.ensure_one()
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'lugares.interes.historia'),
            ('res_id', '=', self.id),
            ('res_field', '=', 'image_main_grid')
        ], limit=1)
        if attachment:
            return f'/web/content/{attachment.id}'
        return False
    
    def get_image_detail_url(self):
        """Devuelve la URL directa al attachment de image_main_detail"""
        self.ensure_one()
        attachment = self.env['ir.attachment'].search([
            ('res_model', '=', 'lugares.interes.historia'),
            ('res_id', '=', self.id),
            ('res_field', '=', 'image_main_detail')
        ], limit=1)
        if attachment:
            return f'/web/content/{attachment.id}'
        return False
