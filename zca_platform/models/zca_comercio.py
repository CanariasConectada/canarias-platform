from odoo import models, fields, api
from odoo.exceptions import ValidationError

class ZcaComercio(models.Model):
    """Extiende res.partner con campos específicos de ZCA para comercios."""
    _inherit = 'res.partner'

    x_zca_es_comercio = fields.Boolean(
        string='Es comercio ZCA',
        default=False,
    )
    x_zca_slug = fields.Char(
        string='Slug URL',
        help='Identificador único para la URL del microsite',
    )
    x_zca_zona = fields.Selection([
        ('guanarteme', 'Guanarteme'),
        ('lomolosfrailes', 'Lomo Los Frailes'),
        ('tamaraceite', 'Tamaraceite'),
    ], string='Zona Comercial')
    x_zca_tipo = fields.Char(string='Tipo de Negocio')
    x_zca_categoria = fields.Char(string='Categoría')
    x_zca_subcategoria = fields.Char(string='Subcategoría')

    # Horarios y servicios
    x_zca_horario_texto = fields.Char(
        string='Horario',
        help='Para horarios complejos: L,M,X,J,V,S,D 08:00–23:59',
    )
    x_zca_entrega = fields.Char(
        string='Entrega / Envíos',
        help='Describe el servicio de entrega del comercio',
    )
    x_zca_parking = fields.Char(
        string='Parking',
        help='Información sobre aparcamiento',
    )

    # Redes sociales
    x_zca_whatsapp = fields.Char(string='WhatsApp')
    x_zca_instagram = fields.Char(string='Instagram')
    x_zca_tiktok = fields.Char(string='TikTok')

    # Contenido microsite
    x_zca_descripcion_corta = fields.Text(string='Descripción corta')
    x_zca_sec1_texto = fields.Text(string='Texto sección 1')
    x_zca_historia_titulo = fields.Char(string='Título nuestra historia')
    x_zca_historia_texto = fields.Text(string='Texto nuestra historia')
    x_zca_servicio_titulo = fields.Char(string='Título nuestro servicio')
    x_zca_servicio_texto = fields.Text(string='Texto nuestro servicio')

    # Imágenes (URLs externas o paths)
    x_zca_hero_imagen_url = fields.Char(
        string='URL imagen hero',
        help='URL o path de la imagen hero del microsite',
    )
    x_zca_sec1_imagen_url = fields.Char(string='URL imagen sección 1')
    x_zca_sec2_imagen_url = fields.Char(string='URL imagen sección 2')

    # URLs
    x_zca_microsite_url = fields.Char(string='URL microsite')

    # Relación con website de Odoo
    x_zca_website_id = fields.Many2one(
        'website',
        string='Website del comercio',
        help='El website de Odoo asignado a este comercio',
    )

    # Campos legacy preservados para compatibilidad
    x_zca_horario_lv = fields.Char(string='Horario L-V')
    x_zca_horario_sab = fields.Char(string='Horario Sábado')
    x_zca_horario_dom = fields.Char(string='Horario Domingo')
    x_zca_descripcion_larga = fields.Text(string='Descripción larga')
    x_zca_portada_imagen_url = fields.Char(string='URL imagen portada (legacy)')
    x_zca_cta_texto = fields.Char(string='Texto CTA personalizado')
    x_zca_score_joven = fields.Integer(string='Score Joven', default=5)
    x_zca_score_familiar = fields.Integer(string='Score Familiar', default=5)
    x_zca_score_turistico = fields.Integer(string='Score Turístico', default=5)
    x_zca_review_google = fields.Float(string='Puntuación Google', digits=(3, 1))
    x_zca_review_tripadvisor = fields.Float(string='Puntuación TripAdvisor', digits=(3, 1))
    x_zca_accesibilidad_silla = fields.Boolean(string='Accesible silla de ruedas')
    x_zca_accesibilidad_mayores = fields.Boolean(string='Accesible mayores')
    x_zca_accesibilidad_ninos = fields.Boolean(string='Apto para niños')

