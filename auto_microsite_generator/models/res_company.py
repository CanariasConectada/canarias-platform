# -*- coding: utf-8 -*-
import re
from odoo import api, models

# Parent / protected company names that should NOT get auto-microsite
_PROTECTED_NAME_PATTERNS = [
    'zona comercial',
    'canarias conectada',
    'admin',
    'my company',
]

# Template defaults (real content, not Lorem Ipsum)
_TEMPLATE_DEFAULTS = {
    'microsite_acerca1_titulo': 'Sobre nosotros',
    'microsite_acerca1_texto': (
        'En nuestro espacio encontrarás productos y servicios seleccionados con dedicación. '
        'Visítanos y forma parte de la experiencia Canarias Conectada.'
    ),
    'microsite_acerca2_titulo': 'Nuestros servicios',
    'microsite_acerca2_texto': (
        'En nuestro espacio encontrarás productos y servicios seleccionados con dedicación. '
        'Visítanos y forma parte de la experiencia Canarias Conectada.'
    ),
    'microsite_button_text': 'Tienda',
    'microsite_separador_titulo': 'Consume Productos Canarios',
    'microsite_address': 'Las Palmas de Gran Canaria',
    'microsite_entrega': 'Entrega disponible',
    'microsite_parking': 'Parking cercano',
    'microsite_horario': 'L-V 09:00-17:00 / S 10:00-12:00',
}

# Theme view keys that must be copied to every new microsite website
_THEME_VIEW_KEYS = [
    'theme_corporate_multi.corporate_footer',
    'theme_corporate_multi.corporate_header',
    'theme_corporate_multi.corporate_remove_copyright',
    'theme_corporate_multi.hide_header_elements_css',
    'theme_corporate_multi.clean_directory_menus_assets',
]


def _normalize_subdomain(name):
    """Generate a safe subdomain from company name."""
    subdomain = name.lower()
    subdomain = re.sub(r'[^a-z0-9\s]', '', subdomain)
    subdomain = re.sub(r'\s+', '', subdomain)
    subdomain = subdomain[:30]
    return subdomain or 'empresa'


class ResCompany(models.Model):
    _inherit = 'res.company'

    @api.model_create_multi
    def create(self, vals_list):
        companies = super().create(vals_list)
        current_allowed = list(self.env.context.get('allowed_company_ids') or [self.env.company.id])
        new_ids = [c.id for c in companies if c.id not in current_allowed]
        extended_ctx = dict(self.env.context, allowed_company_ids=current_allowed + new_ids) if new_ids else self.env.context
        for company in companies.with_context(extended_ctx):
            if company.env.context.get('no_microsite_auto'):
                continue
            if company.website_id:
                continue
            name_lower = (company.name or '').lower()
            if any(p in name_lower for p in _PROTECTED_NAME_PATTERNS):
                continue
            company._auto_create_microsite(company)
        return companies

    def _auto_create_microsite(self, company):
        """Create website + default content + theme views for a new company."""
        self.ensure_one()
        partner = company.partner_id
        if not partner:
            return

        subdomain = _normalize_subdomain(company.name)
        domain = f'https://{subdomain}.canariasconectada.es'

        # Check for theme
        Theme = self.env['ir.module.module'].sudo()
        theme = Theme.search([('name', '=', 'theme_corporate_multi')], limit=1)
        theme_id = theme and theme.id or False

        # Create website
        website = self.env['website'].sudo().create({
            'name': company.name,
            'domain': domain,
            'company_id': company.id,
            'theme_id': theme_id,
        })

        # Link website to company (sudo para evitar AccessError si la nueva compañía no está en allowed_company_ids)
        company.sudo().write({'website_id': website.id})

        # Copy theme views (footer, header, etc.) to the new website
        self._copy_theme_views_to_website(website)

        # Setup correct menu structure (avoid Odoo default menu with unwanted items)
        self._setup_microsite_menu(website)

        # Build template defaults with company-specific text
        defaults = dict(_TEMPLATE_DEFAULTS)
        defaults['microsite_name'] = company.name
        defaults['microsite_sec1_texto'] = f'Bienvenidos a {company.name}'

        # Write only empty fields to avoid overwriting user data
        vals = {}
        for field, default_val in defaults.items():
            current = getattr(partner, field, None)
            if not current or str(current).lower() in ('false', 'none', ''):
                vals[field] = default_val

        if vals:
            partner.write(vals)

        # Generate homepage view + page
        partner._sync_to_website()

        # Ensure website.page exists (workaround for _sync_to_website bug)
        View = self.env['ir.ui.view'].sudo()
        Page = self.env['website.page'].sudo()
        page = Page.search([('website_id', '=', website.id), ('url', '=', '/')], limit=1)
        if not page:
            view = View.search([
                ('key', '=', f'website.homepage_{subdomain}'),
                ('website_id', '=', website.id),
            ], limit=1)
            if view:
                Page.create({
                    'url': '/',
                    'view_id': view.id,
                    'website_id': website.id,
                    'is_published': True,
                })

    def _copy_theme_views_to_website(self, website):
        """Copy theme_corporate_multi views (footer, header, etc.) to a website."""
        View = self.env['ir.ui.view'].sudo()
        for key in _THEME_VIEW_KEYS:
            # Skip if website already has this view
            existing = View.search([
                ('key', '=', key),
                ('website_id', '=', website.id),
            ], limit=1)
            if existing:
                continue

            # Find template view (lowest ID = original)
            template = View.search([
                ('key', '=', key),
            ], order='id asc', limit=1)

            if not template:
                continue

            View.create({
                'name': template.name,
                'key': key,
                'type': 'qweb',
                'arch_db': template.arch_db,
                'inherit_id': template.inherit_id.id,
                'mode': template.mode,
                'priority': template.priority,
                'active': True,
                'website_id': website.id,
            })

    def _setup_microsite_menu(self, website):
        """Ensure the microsite has the standard menu (no Memoria Viva/Eventos)."""
        Menu = self.env['website.menu'].sudo()

        root = Menu.search([
            ('website_id', '=', website.id),
            ('parent_id', '=', False),
        ], limit=1)

        if not root:
            return

        # Remove unwanted menus
        unwanted = Menu.search([
            ('parent_id', '=', root.id),
            ('name', 'in', ['Memoria Viva', 'Eventos']),
        ])
        if unwanted:
            unwanted.unlink()

        # Rename Directorio -> Comercios
        directorio = Menu.search([
            ('parent_id', '=', root.id),
            ('name', '=', 'Directorio'),
        ], limit=1)
        if directorio:
            directorio.write({'name': 'Comercios'})

        # Ensure standard items exist
        expected = [
            ('Inicio', '/', 10),
            ('Tienda', '/shop', 20),
            ('Comercios', '/directorio', 30),
        ]
        for name, url, seq in expected:
            existing = Menu.search([
                ('parent_id', '=', root.id),
                ('name', '=', name),
            ], limit=1)
            if not existing:
                Menu.create({
                    'name': name,
                    'url': url,
                    'parent_id': root.id,
                    'website_id': website.id,
                    'sequence': seq,
                })

        # Ensure Zonas Comerciales with submenus
        zonas = Menu.search([
            ('parent_id', '=', root.id),
            ('name', '=', 'Zonas Comerciales'),
        ], limit=1)
        if not zonas:
            zonas = Menu.create({
                'name': 'Zonas Comerciales',
                'url': '#',
                'parent_id': root.id,
                'website_id': website.id,
                'sequence': 40,
            })

        expected_zonas = [
            ('Canarias Conectada', 'https://canariasconectada.es', 0),
            ('Guanarteme', 'https://guanarteme.canariasconectada.es', 1),
            ('Lomo Los Frailes', 'https://lomolosfrailes.canariasconectada.es', 2),
            ('Tamaraceite', 'https://tamaraceite.canariasconectada.es', 3),
        ]
        for name, url, seq in expected_zonas:
            sub = Menu.search([
                ('parent_id', '=', zonas.id),
                ('name', '=', name),
            ], limit=1)
            if not sub:
                Menu.create({
                    'name': name,
                    'url': url,
                    'parent_id': zonas.id,
                    'website_id': website.id,
                    'sequence': seq,
                })
