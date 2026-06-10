# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date


class LugaresInteresAnuncio(models.Model):
    _name = 'lugares.interes.anuncio'
    _description = 'Anuncio/Oferta - Lugares de Interés'
    _order = 'sequence, id'
    _rec_name = 'name'

    # ========================================
    # CAMPOS PRINCIPALES
    # ========================================
    name = fields.Char(string='Título', required=True, index=True)
    description = fields.Text(string='Descripción')
    image = fields.Image(string='Imagen', required=True, attachment=True)
    url = fields.Char(string='Enlace', help='URL al que redirige el anuncio al hacer clic')
    
    # Website
    website_id = fields.Many2one('website', string='Website', required=True, 
                                  default=lambda self: self.env.ref('website.default_website', raise_if_not_found=False),
                                  help='Website donde se mostrará el anuncio')
    
    # Posición y dimensiones
    position = fields.Selection([
        ('hero_bottom', 'Debajo del Hero'),
        ('sidebar', 'Barra lateral'),
        ('footer', 'Pie de página'),
        ('list_top', 'Arriba del listado'),
        ('list_bottom', 'Debajo del listado'),
    ], string='Posición', default='hero_bottom', required=True)
    
    size = fields.Selection([
        ('small', 'Pequeño (25% ancho)'),
        ('medium', 'Mediano (50% ancho)'),
        ('large', 'Grande (75% ancho)'),
        ('full', 'Completo (100% ancho)'),
    ], string='Tamaño', default='medium', required=True, 
       help='Ancho que ocupará el anuncio en la página')
    
    # Fechas de publicación
    date_start = fields.Date(string='Fecha inicio', required=True, default=fields.Date.today)
    date_end = fields.Date(string='Fecha fin', help='Dejar vacío para no tener fecha de fin')
    
    # Estado
    state = fields.Selection([
        ('activo', 'Activo'),
        ('inactivo', 'Inactivo'),
        ('programado', 'Programado'),
    ], string='Estado', default='activo', required=True)
    
    sequence = fields.Integer(string='Secuencia', default=10, 
                               help='Orden de visualización (menor = primero)')
    active = fields.Boolean(string='Activo', default=True)
    
    # Contador de clics (analytics básico)
    click_count = fields.Integer(string='Clics', default=0, readonly=True)

    # ========================================
    # COMPUTE FIELDS
    # ========================================
    is_visible = fields.Boolean(string='Visible hoy', compute='_compute_is_visible', store=True)
    size_class = fields.Char(string='Clase CSS tamaño', compute='_compute_size_class')
    
    @api.depends('state', 'date_start', 'date_end', 'active')
    def _compute_is_visible(self):
        today = date.today()
        for record in self:
            if not record.active or record.state == 'inactivo':
                record.is_visible = False
            elif record.state == 'programado' and record.date_start > today:
                record.is_visible = False
            elif record.date_end and record.date_end < today:
                record.is_visible = False
            else:
                record.is_visible = True
    
    def _compute_size_class(self):
        size_classes = {
            'small': 'col-md-3 col-sm-6',
            'medium': 'col-md-6 col-sm-12',
            'large': 'col-md-9 col-sm-12',
            'full': 'col-12',
        }
        for record in self:
            record.size_class = size_classes.get(record.size, 'col-md-6 col-sm-12')

    # ========================================
    # VALIDACIONES
    # ========================================
    @api.constrains('date_start', 'date_end')
    def _check_dates(self):
        for record in self:
            if record.date_end and record.date_start > record.date_end:
                raise ValidationError(_('La fecha de inicio no puede ser posterior a la fecha de fin.'))
    
    @api.constrains('url')
    def _check_url(self):
        for record in self:
            if record.url and not (record.url.startswith('http://') or record.url.startswith('https://') or record.url.startswith('/')):
                raise ValidationError(_('La URL debe comenzar con http://, https:// o /'))

    # ========================================
    # MÉTODOS
    # ========================================
    def action_activar(self):
        self.write({'state': 'activo'})
    
    def action_desactivar(self):
        self.write({'state': 'inactivo'})
    
    def action_programar(self):
        self.write({'state': 'programado'})
    
    def increment_click(self):
        """Incrementa el contador de clics (llamado desde controller)"""
        self.sudo().write({'click_count': self.click_count + 1})

    # ========================================
    # CRON: Actualizar estado programados
    # ========================================
    @api.model
    def _cron_actualizar_estados(self):
        """Cron job para activar anuncios programados cuya fecha llegó"""
        today = date.today()
        # Activar programados que llegaron a su fecha
        anuncios = self.search([
            ('state', '=', 'programado'),
            ('date_start', '<=', today),
        ])
        anuncios.write({'state': 'activo'})
        
        # Desactivar anuncios que pasaron su fecha fin
        anuncios_vencidos = self.search([
            ('state', '=', 'activo'),
            ('date_end', '!=', False),
            ('date_end', '<', today),
        ])
        anuncios_vencidos.write({'state': 'inactivo'})
