import logging

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    zone_id = fields.Many2one(
        'zone',
        string='Zona',
        related='company_id.zone_id',
        store=True,
        readonly=True,
        index=True,
        help='Zona a la que pertenece el producto (heredada de la compañía)'
    )

    # ============================================================
    # REFLEJO AUTOMÁTICO: Invalidar has_published_products de categorías
    # ============================================================
    
    def _invalidate_category_has_published(self, old_categories=None):
        """
        Invalida el campo has_published_products de las categorías afectadas.
        
        Esto fuerza el recálculo de has_published_products para que las categorías
        aparezcan/desaparezcan del sidebar en tiempo real cuando:
        - Un producto se asigna/desasigna de una categoría
        - Un producto cambia de estado publicado
        - Un producto cambia de compañía (zona)
        """
        self.ensure_one()
        
        # Obtener categorías actuales del producto
        current_categories = self.public_categ_ids
        
        # Si hay categorías previas (para casos de write), incluirlas también
        categories_to_invalidate = current_categories
        if old_categories:
            categories_to_invalidate = current_categories | old_categories
        
        if not categories_to_invalidate:
            return
        
        # Obtener todas las categorías afectadas incluyendo padres
        # Las categorías padre también deben recalcularse porque pueden
        # quedar sin productos si se remueve el último hijo
        all_categories = self.env['product.public.category']
        for cat in categories_to_invalidate:
            all_categories |= cat
            # Incluir padres (para recalcular si aún tienen productos)
            all_categories |= cat.parents_and_self
            # Incluir hijos (para recalcular su estado)
            all_categories |= cat.child_id
        
        if all_categories:
            _logger.info(
                f"[ZONES CATEGORY] Invalidando has_published_products para {len(all_categories)} "
                f"categorías afectadas por cambio en producto {self.name} ({self.id})"
            )
            # Invalidar el campo para forzar recálculo
            all_categories.invalidate_recordset(['has_published_products'])
    
    @api.model_create_multi
    def create(self, vals_list):
        """
        Sobrescribe create para invalidar categorías cuando se crea un producto
        con categorías asignadas o publicado.
        """
        products = super().create(vals_list)
        
        for product in products:
            # Solo invalidar si el producto está publicado y tiene categorías
            if product.is_published and product.public_categ_ids:
                product._invalidate_category_has_published()
        
        return products
    
    def write(self, vals):
        """
        Sobrescribe write para detectar cambios en:
        - public_categ_ids: categorías asignadas al producto
        - is_published: estado de publicación
        - company_id: compañía (afecta la zona)
        
        E invalidar has_published_products de las categorías afectadas.
        """
        # Guardar categorías previas antes del write
        old_categories_by_product = {}
        if 'public_categ_ids' in vals or 'is_published' in vals or 'company_id' in vals:
            for product in self:
                old_categories_by_product[product.id] = product.public_categ_ids
        
        result = super().write(vals)
        
        # Detectar qué cambios requieren invalidación
        invalidate_fields = ['public_categ_ids', 'is_published', 'company_id']
        if any(field in vals for field in invalidate_fields):
            for product in self:
                old_cats = old_categories_by_product.get(product.id)
                # Invalidar siempre que haya cambiado algo relevante
                product._invalidate_category_has_published(old_categories=old_cats)
        
        return result
    
    def unlink(self):
        """
        Sobrescribe unlink para invalidar categorías antes de eliminar el producto.
        """
        for product in self:
            if product.is_published and product.public_categ_ids:
                product._invalidate_category_has_published()
        
        return super().unlink()
