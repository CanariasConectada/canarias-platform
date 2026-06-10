import logging

from odoo import models, fields, api, _
from odoo.fields import Domain

_logger = logging.getLogger(__name__)


class Website(models.Model):
    _inherit = 'website'

    zone_id = fields.Many2one(
        'zone',
        string='Zona',
        ondelete='set null',
        index=True,
        help='Zona asignada a este website. Los productos de compañías de esta zona serán visibles.'
    )
    
    is_canarias_conectada = fields.Boolean(
        string='Es Canarias Conectada',
        compute='_compute_is_canarias_conectada',
        store=False,  # Usar valor calculado dinámicamente
        help='Indica si este website es Canarias Conectada (dominio exacto https://canariasconectada.es)'
    )

    @api.model
    def _setup_microsite_zones(self):
        """
        Configura las zonas para los microsites.
        Este método se llama desde el archivo de datos XML.
        """
        # Buscar zonas por código
        Zone = self.env['zone']
        
        zone_gua = Zone.search([('code', '=', 'GUA')], limit=1)
        zone_tam = Zone.search([('code', '=', 'TAM')], limit=1)
        zone_lom = Zone.search([('code', '=', 'LOM')], limit=1)
        
        # Configurar websites
        websites = self.search([])
        
        for website in websites:
            domain = website.domain or ''
            
            # Canarias Conectada - sin zona (muestra todo)
            if 'canariasconectada' in domain.lower():
                if website.zone_id:
                    website.zone_id = False
                    _logger.debug(f"Configurado {website.name} como Canarias Conectada (sin zona)")
            
            # Guanarteme
            elif 'guanarteme' in domain.lower() or 'guanartme' in domain.lower() or 'zcaguanarteme' in domain.lower():
                if zone_gua and website.zone_id != zone_gua:
                    website.zone_id = zone_gua
                    _logger.debug(f"Configurado {website.name} con zona Guanarteme")
            
            # Tamaraceite
            elif 'tamaraceite' in domain.lower() or 'ztamaraceite' in domain.lower():
                if zone_tam and website.zone_id != zone_tam:
                    website.zone_id = zone_tam
                    _logger.debug(f"Configurado {website.name} con zona Tamaraceite")
            
            # Lomo los Frailes
            elif 'lomofrailes' in domain.lower() or 'frailes' in domain.lower() or 'zlomolosfrailes' in domain.lower():
                if zone_lom and website.zone_id != zone_lom:
                    website.zone_id = zone_lom
                    _logger.debug(f"Configurado {website.name} con zona Lomo los Frailes")

    @api.depends('domain')
    def _compute_is_canarias_conectada(self):
        """
        Canarias Conectada se identifica ÚNICAMENTE por tener el dominio EXACTO:
        'https://canariasconectada.es'
        
        Ningún otro dominio (incluyendo subdominios como guanarteme.canariasconectada.es)
        debe ser considerado Canarias Conectada.
        """
        for website in self:
            domain = website.domain or ''
            # Solo el dominio exacto es Canarias Conectada
            website.is_canarias_conectada = domain == 'https://canariasconectada.es'

    def _get_zone_companies(self):
        """
        Obtiene las compañías que pertenecen a la zona de este website.
        Si es Canarias Conectada, devuelve todas las compañías.
        """
        self.ensure_one()
        
        if self.is_canarias_conectada:
            # Canarias Conectada muestra todas las compañías
            return self.env['res.company'].sudo().search([])
        
        if not self.zone_id:
            return self.env['res.company']
        
        # Usar sudo() para evitar restricciones multi-company del usuario actual
        return self.env['res.company'].sudo().search([
            ('zone_id', '=', self.zone_id.id)
        ])

    def _get_zone_company_ids(self):
        """Devuelve los IDs de las compañías de la zona."""
        return self._get_zone_companies().ids
    
    def _get_zone_product_domain_list(self):
        """
        Construye el dominio para filtrar productos de la zona.
        Retorna una lista de tuplas (formato clásico de Odoo).
        """
        self.ensure_one()
        
        if self.is_canarias_conectada:
            # Canarias Conectada: todos los productos publicados
            return [('is_published', '=', True)]
        
        company_ids = self._get_zone_company_ids()
        if not company_ids:
            return [('id', '=', False)]  # No hay productos si no hay compañías
        
        return [
            ('is_published', '=', True),
            ('company_id', 'in', company_ids),
        ]
    
    def _get_zone_category_domain(self):
        """
        Construye el dominio para filtrar categorías de la zona.
        Retorna una lista de tuplas.
        
        Este método ahora usa sudo() para obtener todos los productos de la zona,
        independientemente de las reglas de acceso del usuario actual.
        """
        self.ensure_one()
        
        if self.is_canarias_conectada:
            # Canarias Conectada: todas las categorías con productos publicados
            return [('has_published_products', '=', True)]
        
        company_ids = self._get_zone_company_ids()
        if not company_ids:
            return [('id', '=', False)]  # No hay categorías si no hay compañías
        
        # Buscar productos de la zona usando sudo() para evitar restricciones de acceso
        products = self.env['product.template'].sudo().search([
            ('is_published', '=', True),
            ('company_id', 'in', company_ids),
        ])
        
        if not products:
            return [('id', '=', False)]
        
        # Obtener todas las categorías de estos productos, incluyendo padres
        category_ids = set()
        for product in products:
            for cat in product.public_categ_ids:
                category_ids.add(cat.id)
                # Incluir todos los padres de la categoría
                category_ids.update(cat.parents_and_self.ids)
        
        if not category_ids:
            return [('id', '=', False)]
        
        return [
            '|',
            ('id', 'in', list(category_ids)),
            ('id', 'parent_of', list(category_ids)),
        ]

    def get_pricelist_available(self, show_visible=False):
        """Sobreescribe para filtrar tarifas por compañías de la zona."""
        self.ensure_one()
        
        pricelists = super().get_pricelist_available(show_visible=show_visible)
        
        if self.is_canarias_conectada:
            return pricelists
        
        # Filtrar tarifas por compañías de la zona
        company_ids = self._get_zone_company_ids()
        if company_ids:
            pricelists = pricelists.filtered(
                lambda pl: not pl.company_id or pl.company_id.id in company_ids
            )
        
        return pricelists

    def _search_get_details(self, search_type, order, options):
        """
        Sobreescribe para aplicar filtros de zona en las búsquedas (autocomplete).
        """
        _logger.debug(f"[ZONES DEBUG] _search_get_details llamado para {self.name}, search_type={search_type}")
        
        search_details = super()._search_get_details(search_type, order, options)
        
        _logger.debug(f"[ZONES DEBUG] Modelos en search_details: {[d.get('model') for d in search_details]}")
        
        # Para zonas, necesitamos modificar el dominio de productos
        if search_type in ['products', 'products_only', 'all']:
            if self.zone_id or self.is_canarias_conectada:
                for detail in search_details:
                    if detail.get('model') == 'product.template':
                        if self.is_canarias_conectada:
                            # Canarias Conectada: todos los productos publicados
                            detail['base_domain'] = [
                                ('sale_ok', '=', True),
                                ('is_published', '=', True),
                            ]
                            _logger.debug(f"[ZONES] Dominio autocomplete para Canarias Conectada: {detail['base_domain']}")
                        elif self.zone_id:
                            company_ids = self._get_zone_company_ids()
                            if company_ids:
                                # Reemplazar el dominio base con uno que filtre por compañías de la zona
                                detail['base_domain'] = [
                                    ('sale_ok', '=', True),
                                    ('is_published', '=', True),
                                    ('company_id', 'in', company_ids),
                                ]
                                _logger.debug(f"[ZONES] Dominio autocomplete para zona {self.zone_id.name}: {detail['base_domain']}")
        
        return search_details

    def sale_product_domain(self):
        """
        Sobreescribe para filtrar productos según el tipo de website.
        
        Comportamiento:
        1. Canarias Conectada: TODOS los productos publicados
        2. Zona comercial: productos de las compañías de la zona
        3. Microsite individual: SOLO productos de su propia compañía
        """
        import logging
        import sys
        logging.info(f"[ZONES DEBUG] === INICIO sale_product_domain() ===")
        _logger.debug(f"[ZONES DEBUG] sale_product_domain() llamado para {self.name}, "
                    f"zone_id={self.zone_id.id if self.zone_id else None}, "
                    f"is_canarias={self.is_canarias_conectada}")
        
        # CASO 1: Canarias Conectada - mostrar TODOS los productos
        if self.is_canarias_conectada:
            domain = [
                ('sale_ok', '=', True),
                ('is_published', '=', True),
            ]
            if not self.env.user._is_internal():
                domain.append(('service_tracking', 'in', self.env['product.template']._get_saleable_tracking_types()))
            _logger.debug(f"[ZONES DEBUG] Dominio Canarias Conectada: {domain}")
            return domain
        
        # CASO 2: Zona comercial - productos de las compañías de la zona
        if self.zone_id:
            company_ids = self._get_zone_company_ids()
            if not company_ids:
                _logger.debug(f"[ZONES DEBUG] No hay compañías en la zona")
                return [('id', '=', False)]
            
            domain = [
                ('sale_ok', '=', True),
                ('company_id', 'in', company_ids),
            ]
            if not self.env.user._is_internal():
                domain.extend([
                    ('is_published', '=', True),
                    ('service_tracking', 'in', self.env['product.template']._get_saleable_tracking_types()),
                ])
            _logger.debug(f"[ZONES DEBUG] Dominio zona para {self.name}: {domain}")
            return domain
        
        # CASO 3: Microsite individual - SOLO productos de su compañía
        domain = [
            ('sale_ok', '=', True),
            ('company_id', '=', self.company_id.id),
        ]
        if not self.env.user._is_internal():
            domain.extend([
                ('is_published', '=', True),
                ('service_tracking', 'in', self.env['product.template']._get_saleable_tracking_types()),
            ])
        _logger.debug(f"[ZONES DEBUG] Dominio microsite individual {self.name}: {domain}")
        return domain

    def website_domain(self):
        """
        Sobreescribe para ignorar el filtro de website_id en microsites de zonas.
        """
        # Para microsites con zona específica, no filtrar por website_id
        # Esto permite ver productos de todas las compañías de la zona
        if self.zone_id:
            # Verificar que no sea Canarias Conectada (que no tiene zona)
            domain_str = self.domain or ''
            is_canarias = 'canariasconectada' in domain_str.lower()
            
            if not is_canarias:
                _logger.debug(f"[ZONES] website_domain() para {self.name} - ignorando website_id")
                # Retornar dominio neutro que no filtre nada
                return Domain([('id', '!=', 0)])
        
        _logger.debug(f"[ZONES] website_domain() para {self.name} - comportamiento normal")
        return super().website_domain()

    @api.model
    def _get_product_sort_mapping(self):
        """
        Sobreescribe para agregar la opción de orden aleatorio (Mezclar).
        """
        mapping = super()._get_product_sort_mapping()
        
        # Agregar opción de mezclar al principio
        # Usamos 'shuffle' como identificador especial
        shuffle_option = ('shuffle', _("Mezclar productos"))
        
        # Insertar después de la primera opción (Featured)
        return mapping[:1] + [shuffle_option] + mapping[1:]
