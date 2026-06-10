import logging

from odoo import models, fields, api
from odoo.http import request

_logger = logging.getLogger(__name__)


class ProductPublicCategory(models.Model):
    _inherit = 'product.public.category'

    zone_ids = fields.Many2many(
        'zone',
        string='Zonas',
        compute='_compute_zone_ids',
        store=False,
        help='Zonas a las que pertenecen los productos de esta categoría'
    )
    
    zone_company_ids = fields.Many2many(
        'res.company',
        string='Compañías de la Zona',
        compute='_compute_zone_company_ids',
        store=False,
    )

    @api.depends('product_tmpl_ids', 'product_tmpl_ids.company_id', 'product_tmpl_ids.company_id.zone_id')
    def _compute_zone_ids(self):
        """Calcula las zonas a las que pertenecen los productos de esta categoría."""
        for category in self:
            zones = category.product_tmpl_ids.mapped('company_id.zone_id')
            category.zone_ids = zones

    @api.depends('product_tmpl_ids', 'product_tmpl_ids.company_id')
    def _compute_zone_company_ids(self):
        """Calcula las compañías de los productos de esta categoría."""
        for category in self:
            category.zone_company_ids = category.product_tmpl_ids.mapped('company_id')

    # ============================================================
    # FIX: Categorías en sidebar para usuarios portal en zonas
    # ============================================================
    
    @api.model
    def _search_has_published_products(self, operator, value):
        """
        Sobrescribe la búsqueda de categorías con productos publicados.
        
        Para usuarios portal en zonas (Guanarteme, Tamaraceite, Lomo los Frailes)
        o Canarias Conectada, necesitamos considerar TODOS los productos de la zona,
        no solo los de la empresa del usuario (que es lo que las reglas de acceso
        devuelven por defecto).
        """
        # Verificar si estamos en un contexto de website con zona
        if hasattr(request, 'website') and request.website:
            website = request.website
            if website.zone_id or website.is_canarias_conectada:
                _logger.debug(f"[ZONES CATEGORY] Usando búsqueda de categorías para zona/Canarias: {website.name}")
                
                # Obtener company_ids de la zona
                if website.is_canarias_conectada:
                    # Canarias Conectada: todas las compañías
                    company_ids = self.env['res.company'].sudo().search([]).ids
                else:
                    # Zona específica
                    company_ids = website._get_zone_company_ids()
                
                if not company_ids:
                    _logger.debug("[ZONES CATEGORY] No hay compañías en la zona, devolviendo dominio vacío")
                    return [('id', '=', False)]
                
                # Buscar categorías directamente desde SQL para evitar filtros de website
                # Los productos pueden tener website_id restringido que excluye la búsqueda
                self.env.cr.execute("""
                    SELECT DISTINCT pc.id 
                    FROM product_public_category pc
                    JOIN product_public_category_product_template_rel rel ON rel.product_public_category_id = pc.id
                    JOIN product_template pt ON rel.product_template_id = pt.id
                    WHERE pt.is_published = true
                    AND pt.company_id = ANY(%s)
                """, (company_ids,))
                
                category_ids = set(row[0] for row in self.env.cr.fetchall())
                
                _logger.debug(f"[ZONES CATEGORY] Encontradas {len(category_ids)} categorías por SQL")
                
                # Incluir padres de las categorías encontradas
                if category_ids:
                    parent_ids = set()
                    for cat_id in list(category_ids):
                        self.env.cr.execute("""
                            SELECT parent_id FROM product_public_category
                            WHERE id = %s AND parent_id IS NOT NULL
                        """, (cat_id,))
                        row = self.env.cr.fetchone()
                        if row and row[0]:
                            parent_ids.add(row[0])
                    category_ids.update(parent_ids)
                
                # Devolver dominio que incluye estas categorías y sus padres
                result_domain = [
                    '|',
                    ('id', 'in', list(category_ids)),
                    ('id', 'parent_of', list(category_ids)),
                ]
                return result_domain
        
        # Contexto normal: usar comportamiento estándar
        return super()._search_has_published_products(operator, value)

    @api.depends('product_tmpl_ids.is_published', 'child_id.has_published_products')
    def _compute_has_published_products(self):
        """
        Sobrescribe el cálculo de has_published_products.
        
        Para usuarios portal en zonas o Canarias Conectada, calcula el valor
        considerando todos los productos de la zona, no solo los visibles
        por las reglas de acceso del usuario.
        """
        # Verificar si estamos en un contexto de website con zona
        website = None
        try:
            if hasattr(request, 'website') and request.website:
                website = request.website
        except Exception:
            pass
        
        if website and (website.zone_id or website.is_canarias_conectada):
            _logger.debug(f"[ZONES CATEGORY] Computando has_published_products para zona/Canarias: {website.name}")
            
            # Obtener company_ids de la zona
            if website.is_canarias_conectada:
                company_ids = self.env['res.company'].sudo().search([]).ids
            else:
                company_ids = website._get_zone_company_ids()
            
            if company_ids:
                # Buscar categorías directamente desde SQL para evitar filtros de website
                self.env.cr.execute("""
                    SELECT DISTINCT pc.id 
                    FROM product_public_category pc
                    JOIN product_public_category_product_template_rel rel ON rel.product_public_category_id = pc.id
                    JOIN product_template pt ON rel.product_template_id = pt.id
                    WHERE pt.is_published = true
                    AND pt.company_id = ANY(%s)
                """, (company_ids,))
                
                published_category_ids = set(row[0] for row in self.env.cr.fetchall())
                
                # Incluir padres de las categorías encontradas
                if published_category_ids:
                    for cat_id in list(published_category_ids):
                        self.env.cr.execute("""
                            SELECT parent_id FROM product_public_category
                            WHERE id = %s AND parent_id IS NOT NULL
                        """, (cat_id,))
                        row = self.env.cr.fetchone()
                        if row and row[0]:
                            published_category_ids.add(row[0])
                
                _logger.debug(f"[ZONES CATEGORY] {len(published_category_ids)} categorías con productos en la zona")
                
                # Asignar has_published_products
                for category in self:
                    has_published = category.id in published_category_ids
                    # También verificar hijos
                    if not has_published:
                        has_published = any(
                            c.id in published_category_ids 
                            for c in category.child_id
                        )
                    category.has_published_products = has_published
                return
        
        # Contexto normal: usar comportamiento estándar
        return super()._compute_has_published_products()

    # ============================================================
    # REFLEJO AUTOMÁTICO desde categoría
    # ============================================================
    
    def write(self, vals):
        """
        Sobrescribe write para detectar cambios en product_tmpl_ids
        e invalidar has_published_products de esta categoría y sus padres/hijos.
        """
        if 'product_tmpl_ids' in vals:
            # Guardar categorías afectadas antes del cambio
            categories_to_invalidate = self | self.mapped('parent_id') | self.mapped('child_id')
            _logger.info(
                f"[ZONES CATEGORY] Cambio en product_tmpl_ids de categorías "
                f"{self.ids}, invalidando {len(categories_to_invalidate)} categorías"
            )
            # Invalidar antes del write para que se recalcule después
            categories_to_invalidate.invalidate_recordset(['has_published_products'])
        
        return super().write(vals)
