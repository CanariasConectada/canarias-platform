from odoo import models, api
import logging

_logger = logging.getLogger(__name__)

print("[ZONE_FIX] Loading product_website_published.py")


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    @api.depends('is_published', 'website_id')
    @api.depends_context('website_id')
    def _compute_website_published(self):
        """Sobrescribe para Canarias Conectada: mostrar todos los productos publicados."""
        # Obtener el website actual
        website = self.env['website'].get_current_website()
        is_canarias = hasattr(website, 'is_canarias_conectada') and website.is_canarias_conectada
        is_zone = hasattr(website, 'zone_id') and website.zone_id and website.zone_id.id
        
        if is_canarias or is_zone:
            # Para Canarias Conectada y zonas: website_published = is_published
            # Sin importar el website_id del producto
            for record in self:
                record.website_published = record.is_published
            _logger.info(f"[ZONE_FIX] _compute_website_published: {len(self)} products, is_canarias={is_canarias}, is_zone={bool(is_zone)}, website={website.name}")
        else:
            # Para microsites individuales: comportamiento original
            current_website_id = self.env.context.get('website_id')
            for record in self:
                if current_website_id:
                    record.website_published = record.is_published and (not record.website_id or record.website_id.id == current_website_id)
                else:
                    record.website_published = record.is_published
