from odoo import api, models


class WebsiteMenu(models.Model):
    _inherit = 'website.menu'

    # ============================================================
    # Estructuras de menús por perfil
    # ============================================================

    MENU_STRUCTURE = {
        'canarias': [
            {'name': 'Inicio', 'url': '/', 'sequence': 10, 'children': []},
            {'name': 'Tienda', 'url': '/shop', 'sequence': 20, 'children': []},
            {'name': 'Comercio', 'url': '/directorio', 'sequence': 30, 'children': []},
            {
                'name': 'Zonas Comerciales', 'url': '#', 'sequence': 40,
                'children': [
                    {'name': 'Todas', 'url': 'https://canariasconectada.es', 'sequence': 10},
                    {'name': 'Guanarteme', 'url': 'https://guanarteme.canariasconectada.es', 'sequence': 20},
                    {'name': 'Lomo Los Frailes', 'url': 'https://lomolosfrailes.canariasconectada.es', 'sequence': 30},
                    {'name': 'Tamaraceite', 'url': 'https://tamaraceite.canariasconectada.es', 'sequence': 40},
                ]
            },
            {'name': 'Ferias y Mercadillos', 'url': '/event', 'sequence': 50, 'children': []},
        ],
        'zone': [
            {'name': 'Inicio', 'url': '/', 'sequence': 10, 'children': []},
            {'name': 'Tienda', 'url': '/shop', 'sequence': 20, 'children': []},
            {'name': 'Comercio', 'url': '/directorio', 'sequence': 30, 'children': []},
            {
                'name': 'Zonas Comerciales', 'url': '#', 'sequence': 40,
                'children': [
                    {'name': 'Todas', 'url': 'https://canariasconectada.es', 'sequence': 10},
                    {'name': 'Guanarteme', 'url': 'https://guanarteme.canariasconectada.es', 'sequence': 20},
                    {'name': 'Lomo Los Frailes', 'url': 'https://lomolosfrailes.canariasconectada.es', 'sequence': 30},
                    {'name': 'Tamaraceite', 'url': 'https://tamaraceite.canariasconectada.es', 'sequence': 40},
                ]
            },
            {
                'name': 'Guía Local', 'url': '#', 'sequence': 50,
                'children': [
                    {'name': 'Actividades del barrio', 'url': '/event', 'sequence': 10},
                    {'name': 'Lugares de Interés', 'url': '/lugares-de-interes', 'sequence': 20},
                ]
            },
            {'name': 'Memoria Viva', 'url': '/memoria-viva', 'sequence': 60, 'children': []},
        ],
        'microsite': [
            {'name': 'Inicio', 'url': '/', 'sequence': 10, 'children': []},
            {'name': 'Tienda', 'url': '/shop', 'sequence': 20, 'children': []},
            {'name': 'Comercio', 'url': '/directorio', 'sequence': 30, 'children': []},
            {
                'name': 'Zonas Comerciales', 'url': '#', 'sequence': 40,
                'children': [
                    {'name': 'Todas', 'url': 'https://canariasconectada.es', 'sequence': 10},
                    {'name': 'Guanarteme', 'url': 'https://guanarteme.canariasconectada.es', 'sequence': 20},
                    {'name': 'Lomo Los Frailes', 'url': 'https://lomolosfrailes.canariasconectada.es', 'sequence': 30},
                    {'name': 'Tamaraceite', 'url': 'https://tamaraceite.canariasconectada.es', 'sequence': 40},
                ]
            },
        ],
    }

    @api.model
    def _sync_all_website_menus(self):
        """Sincroniza menús de todos los websites activos."""
        websites = self.env['website'].sudo().search([])
        for website in websites:
            website.menu_id._sync_menus_for_website(website)

    def _sync_menus_for_website(self, website):
        """
        Limpia y recrea menús según el perfil del website.
        Elimina menús existentes para garantizar estructura limpia.
        """
        self.ensure_one()
        profile = website.get_menu_profile()
        structure = self.MENU_STRUCTURE.get(profile, [])

        Menu = self.env['website.menu'].sudo()

        # Limpiar menús existentes del website (excepto el raíz)
        root_menu = website.menu_id
        if root_menu:
            existing = Menu.search([
                ('website_id', '=', website.id),
                ('id', '!=', root_menu.id),
            ])
            if existing:
                existing.unlink()

        # Crear menús base
        for item in structure:
            self._create_or_update_menu_item(website, item, root_menu, {})

        # Gestionar menú de Reseñas
        self._sync_reviews_menu(website, {})

    def _create_or_update_menu_item(self, website, item, parent, existing_by_url):
        """Crea o actualiza un item de menú y sus hijos."""
        Menu = self.env['website.menu'].sudo()
        key = (parent.id, item['url'])
        menu = existing_by_url.get(key)

        vals = {
            'name': item['name'],
            'url': item['url'],
            'sequence': item['sequence'],
            'parent_id': parent.id,
            'website_id': website.id,
        }

        if menu:
            # Solo actualizar si el nombre o secuencia cambió
            if menu.name != item['name'] or menu.sequence != item['sequence']:
                menu.write(vals)
        else:
            menu = Menu.create(vals)
            existing_by_url[(parent.id, item['url'])] = menu

        # Crear hijos
        for child in item.get('children', []):
            self._create_or_update_menu_item(website, child, menu, existing_by_url)

        return menu

    def _sync_reviews_menu(self, website, existing_by_url):
        """Crea o elimina el menú de Reseñas según el flag enable_reviews."""
        Menu = self.env['website.menu'].sudo()
        partner = website.get_reviews_partner()
        show_reviews = partner and partner.enable_reviews

        # Buscar menú de reseñas existente
        reviews_menu = Menu.search([
            ('website_id', '=', website.id),
            ('url', '=', '/resenas'),
        ], limit=1)

        if show_reviews:
            if not reviews_menu:
                # Crear menú de reseñas al final
                last_seq = max(
                    [m.sequence for m in Menu.search([('website_id', '=', website.id), ('parent_id', '=', website.menu_id.id)])]
                    or [0]
                )
                Menu.create({
                    'name': 'Reseñas',
                    'url': '/resenas',
                    'sequence': last_seq + 10,
                    'parent_id': website.menu_id.id,
                    'website_id': website.id,
                })
        else:
            if reviews_menu:
                reviews_menu.unlink()
