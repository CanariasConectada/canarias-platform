# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class WebsiteDirectoryEntry(models.Model):
    _name = 'website.directory.entry'
    _description = 'Directorio de Empresas'
    _order = 'name asc, sequence'
    _inherit = ['website.published.mixin']

    name = fields.Char(string='Nombre', required=True, translate=True)
    sequence = fields.Integer(string='Secuencia', default=10)
    active = fields.Boolean(string='Activo', default=True)
    
    # Relaciones
    company_id = fields.Many2one('res.company', string='Empresa', required=True, ondelete='cascade')
    category_ids = fields.Many2many('business.category', string='Categorías')
    
    # Zona geográfica
    zone = fields.Selection([
        ('canarias', 'Canarias Conectada'),
        ('guanarteme', 'Guanarteme'),
        ('tamaraceite', 'Tamaraceite'),
        ('lomolosfrailes', 'Lomo los Frailes'),
    ], string='Zona', required=True, default='canarias')
    
    # Información de contacto
    description = fields.Text(string='Descripción', translate=True)
    short_description = fields.Char(string='Descripción Corta', translate=True)
    phone = fields.Char(string='Teléfono')
    email = fields.Char(string='Email')
    street = fields.Char(string='Dirección')
    city = fields.Char(string='Ciudad')
    vat = fields.Char(string='NIF/CIF')
    
    # Enlaces externos
    website_url = fields.Char(string='URL del Microsite', compute=False, store=True)
    
    # Imagen - Solo usar imagen propia del entry, no el logo de compañía
    image = fields.Image(string='Logo de Empresa', attachment=True)
    image_1920 = fields.Image(string='Logo 1920', related='image', max_width=1920, max_height=1920, store=True)
    image_1024 = fields.Image(string='Logo 1024', related='image', max_width=1024, max_height=1024, store=True)
    image_512 = fields.Image(string='Logo 512', related='image', max_width=512, max_height=512, store=True)
    image_256 = fields.Image(string='Logo 256', related='image', max_width=256, max_height=256, store=True)
    image_128 = fields.Image(string='Logo 128', related='image', max_width=128, max_height=128, store=True)

    def get_image_url(self):
        """Retorna URL de imagen para el template"""
        self.ensure_one()
        if self.image:
            return f'/web/image/website.directory.entry/{self.id}/image'
        return ''
    
    def get_logo_url(self):
        """Retorna URL del logo - usa company.logo_web si no hay imagen propia"""
        self.ensure_one()
        # Prioridad 1: Imagen propia del entry
        if self.image:
            return f'/web/image/website.directory.entry/{self.id}/image'
        # Prioridad 2: Logo de la compañía vinculada (logo_web es más eficiente)
        if self.company_id and self.company_id.logo_web:
            return f'/directorio/img/{self.id}'
        return ''

    def get_website_url(self):
        """Retorna URL del microsite - v4.0"""
        self.ensure_one()
        if self.website_url:
            if self.website_url.startswith('http'):
                return self.website_url
            return f'https://{self.website_url}'
        return '#'

    def get_display_name(self):
        """Retorna el nombre comercial del partner si existe; si no, el nombre del partner; si no, el name del entry."""
        self.ensure_one()
        partner = self.company_id.partner_id
        if partner:
            return partner.comercial or partner.name or self.name
        return self.name

    @api.constrains('company_id', 'active')
    def _check_company_id_unique(self):
        """Evita duplicados: solo una entrada activa por empresa en el directorio."""
        for entry in self:
            if entry.active and entry.company_id:
                existing = self.env['website.directory.entry'].sudo().search([
                    ('id', '!=', entry.id),
                    ('company_id', '=', entry.company_id.id),
                    ('active', '=', True),
                ], limit=1)
                if existing:
                    raise ValidationError(
                        "La empresa '%s' ya tiene una entrada activa en el directorio (ID %s). "
                        "No se permite duplicados." % (entry.company_id.name, existing.id)
                    )

    def get_category_badge_groups(self):
        """Devuelve grupos de badges jerárquicos para cada categoría asignada.

        Cada grupo es una lista de diccionarios con la cadena padre→hijo
        de una categoría asignada, evitando duplicados visuales.
        """
        self.ensure_one()
        groups = []
        seen_cat_ids = set()
        for cat in self.category_ids:
            # Construir cadena jerárquica de esta categoría
            chain = []
            current = cat
            while current:
                chain.insert(0, current)
                current = current.parent_id
            # Crear badges para esta cadena
            badges = []
            for level, c in enumerate(chain, start=1):
                if c.id not in seen_cat_ids:
                    seen_cat_ids.add(c.id)
                    badges.append({
                        'id': c.id,
                        'name': c.name,
                        'level': level,
                    })
            if badges:
                groups.append(badges)
        return groups
