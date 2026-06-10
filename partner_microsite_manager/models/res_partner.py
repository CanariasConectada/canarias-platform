from odoo import models, fields, api
from odoo.exceptions import UserError
from . import website_builder
import re

_PADRE_IDS_FALLBACK = {258, 259, 260, 262}


def _get_padre_ids(env):
    # Protected website IDs. Configurable via ir.config_parameter key:
    # partner_microsite_manager.padre_website_ids (comma-separated ints)
    try:
        raw = env['ir.config_parameter'].sudo().get_param(
            'partner_microsite_manager.padre_website_ids', ''
        )
        if raw:
            return {int(x.strip()) for x in raw.split(',') if x.strip()}
    except Exception:
        pass
    return _PADRE_IDS_FALLBACK

MICROSITE_FIELDS = [
    'microsite_hero_image',
    'microsite_sec1_image',
    'microsite_sec2_image',
    'microsite_horario',
    'microsite_entrega',
    'microsite_parking',
    'microsite_sec1_texto',
    'microsite_acerca1_titulo',
    'microsite_acerca1_texto',
    'microsite_acerca2_titulo',
    'microsite_acerca2_texto',
    'microsite_separador_titulo',
    'microsite_button_text',
    'microsite_map_url',
    'microsite_name',
    'microsite_email',
    'microsite_phone',
    'microsite_phone2',
    'microsite_address',
    'microsite_facebook',
    'microsite_instagram',
    'microsite_twitter',
    'microsite_linkedin',
    'microsite_youtube',
    'microsite_website',
    'microsite_logo',
    'microsite_favicon',
    'microsite_use_custom_html',
    'microsite_custom_html',
]


class ResPartner(models.Model):
    _inherit = 'res.partner'

    has_microsite = fields.Boolean(compute='_compute_has_microsite')
    microsite_hero_image = fields.Binary(string='Cabecera', attachment=True)
    microsite_sec1_image = fields.Binary(string='Separador 1', attachment=True)
    microsite_sec2_image = fields.Binary(string='Separador 2', attachment=True)
    microsite_horario = fields.Char(string='Horario')
    microsite_entrega = fields.Char(string='Entrega / Envío')
    microsite_parking = fields.Char(string='Dirección / Parking')
    microsite_map_url = fields.Char(string='URL Mapa personalizado')
    microsite_sec1_texto = fields.Text(string='Título Separador 1')
    microsite_acerca1_titulo = fields.Char(string='Título Sección 1 — Sobre nosotros', default='Sobre nosotros')
    microsite_acerca1_texto = fields.Text(string='Contenido Sección 1')
    microsite_acerca2_titulo = fields.Char(string='Título Sección 2 — Servicios', default='Nuestros servicios')
    microsite_acerca2_texto = fields.Text(string='Contenido Sección 2')
    microsite_separador_titulo = fields.Char(string='Título Separador 2', default='Consume Productos Canarios')
    microsite_button_text = fields.Char(string='Texto Botón Hero', default='Tienda')
    microsite_name = fields.Char(string='Nombre del comercio')
    microsite_email = fields.Char(string='Email')
    microsite_phone = fields.Char(string='Teléfono')
    microsite_phone2 = fields.Char(string='Teléfono 2')
    microsite_address = fields.Text(string='Dirección (texto)')
    microsite_facebook = fields.Char(string='Facebook')
    microsite_instagram = fields.Char(string='Instagram')
    microsite_twitter = fields.Char(string='Twitter / X')
    microsite_linkedin = fields.Char(string='LinkedIn')
    microsite_youtube = fields.Char(string='YouTube')
    microsite_website = fields.Char(string='Sitio web')
    microsite_logo = fields.Binary(string='Logo', attachment=False)
    microsite_favicon = fields.Binary(string='Favicon', attachment=False)
    microsite_website_id = fields.Many2one('website', compute='_compute_microsite_website', string='Website')
    microsite_website_url = fields.Char(related='microsite_website_id.domain', string='URL del Microsite', readonly=True)
    microsite_last_sync = fields.Datetime(string='Última sincronización')
    microsite_use_custom_html = fields.Boolean(string='Usar HTML personalizado', default=False)
    microsite_custom_html = fields.Text(string='HTML personalizado de homepage')

    @api.depends()
    def _compute_has_microsite(self):
        companies = self.env['res.company'].search([
            ('partner_id', 'in', self.ids),
            ('website_id', '!=', False),
        ])
        partner_ids_with_site = set(companies.mapped('partner_id.id'))
        for partner in self:
            partner.has_microsite = partner.id in partner_ids_with_site

    @api.depends()
    def _compute_microsite_website(self):
        companies = self.env['res.company'].search([
            ('partner_id', 'in', self.ids),
            ('website_id', '!=', False),
        ])
        mapping = {comp.partner_id.id: comp.website_id for comp in companies}
        for partner in self:
            partner.microsite_website_id = mapping.get(partner.id, False)

    def _get_subdomain_from_website(self):
        self.ensure_one()
        if not self.microsite_website_id:
            return None
        domain = self.microsite_website_id.domain or ''
        domain = domain.replace('https://', '').replace('http://', '').split('/')[0]
        return domain.split('.')[0].lower() if domain else None

    def _get_map_url(self):
        self.ensure_one()
        address_parts = []
        if self.street:
            address_parts.append(str(self.street).replace('&nbsp;', ' '))
        if self.city:
            address_parts.append(str(self.city))
        if self.zip:
            address_parts.append(str(self.zip))
        address = ' '.join(address_parts)
        if address.strip():
            return f"https://maps.google.com/maps?q={address.replace(' ', '+')}&t=&z=13&ie=UTF8&iwloc=&output=embed"
        return "https://maps.google.com/maps?q=Las+Palmas+de+Gran+Canaria&t=&z=13&ie=UTF8&iwloc=&output=embed"

    def read(self, fields=None, load='_classic_read'):
        """Refleja logo y favicon del website en los campos del partner para visualización.
        Si el partner no tiene logo/favicon propio pero el website sí, los muestra en el formulario
        sin alterar la base de datos hasta que el usuario guarde explícitamente."""
        result = super(ResPartner, self).read(fields=fields, load=load)
        if fields is None or 'microsite_logo' in fields or 'microsite_favicon' in fields:
            for record in self:
                website = record.microsite_website_id
                if not website:
                    continue
                res = next((r for r in result if r.get('id') == record.id), None)
                if res is None:
                    continue
                if not res.get('microsite_logo') and website.logo:
                    res['microsite_logo'] = website.logo
                if not res.get('microsite_favicon') and website.favicon:
                    res['microsite_favicon'] = website.favicon
        return result

    def _sync_to_website(self):
        """Genera y actualiza la vista QWeb del website desde los campos del partner."""
        self.ensure_one()
        if not self.has_microsite or self.microsite_website_id.id in _get_padre_ids(self.env):
            return
        if self.env.context.get('no_website_sync'):
            return

        website = self.microsite_website_id
        subdomain = self._get_subdomain_from_website()
        if not subdomain:
            return

        view_key = f'website.homepage_{subdomain}'

        # ── HTML personalizado (toggle) ──
        if self.microsite_use_custom_html:
            custom_html = self.microsite_custom_html or ''
            full_arch = f'''<t name="Home - {subdomain}" t-name="{view_key}">
    <t t-call="website.layout">
        <div id="wrap" class="oe_structure oe_empty">
            {custom_html}
        </div>
    </t>
</t>'''
            View = self.env['ir.ui.view'].sudo()
            Page = self.env['website.page'].sudo()
            view_ids = View.browse()
            page = Page.search([
                ('website_id', '=', website.id),
                ('url', '=', '/'),
            ], limit=1)
            if page:
                view_ids = page.view_id
            if not view_ids:
                view_ids = View.search([
                    ('key', '=', view_key),
                    ('website_id', '=', website.id),
                ], limit=1)
            if not view_ids:
                view_ids = View.search([
                    ('key', 'ilike', f'website.home-{subdomain}%'),
                    ('website_id', '=', website.id),
                ], limit=1)
            if not view_ids:
                view_ids = View.search([
                    ('name', 'ilike', f'Home - {subdomain}'),
                    ('website_id', '=', website.id),
                ], limit=1)
            if not view_ids:
                view_ids = View.search([
                    ('website_id', '=', website.id),
                    ('name', 'ilike', 'Home'),
                ], limit=1)
            if view_ids:
                view_ids.write({'arch_db': full_arch})
            else:
                View.create({
                    'name': f'Home - {subdomain}',
                    'key': view_key,
                    'type': 'qweb',
                    'arch_db': full_arch,
                    'website_id': website.id,
                })
            self._update_theme_footer()
            self.microsite_last_sync = fields.Datetime.now()
            return

        # Obtener RRSS desde website
        rrss = {
            'facebook': website.social_facebook,
            'instagram': website.social_instagram,
            'twitter': website.social_twitter,
            'youtube': website.social_youtube,
            'linkedin': website.social_linkedin,
        }

        company_info = {
            'street': self.street,
            'city': self.city,
            'zip': self.zip,
            'phone': self.microsite_phone or self.phone,
            'email': self.microsite_email or self.email,
            'address': self.microsite_address,
        }
        map_url = self.microsite_map_url or self._get_map_url()

        # Subir imágenes binarias a ir.attachment para obtener IDs
        def upload_image(field_name, image_type):
            data = self[field_name]
            if not data:
                return None
            att_name = f'{subdomain}_{image_type}.jpg'
            # Eliminar attachments previos del mismo nombre para evitar colisión
            existing = self.env['ir.attachment'].sudo().search([
                ('name', '=', att_name),
                ('res_model', '=', 'website'),
                ('res_id', '=', website.id),
            ])
            if existing:
                existing.unlink()
            # Usamos datas (no db_datas directo) para que Odoo gestione checksum
            # y filestore correctamente y las imágenes se sirvan como binarias.
            att = self.env['ir.attachment'].sudo().create({
                'name': att_name,
                'type': 'binary',
                'datas': data,
                'res_model': 'website',
                'res_id': website.id,
                'website_id': website.id,
                'public': True,
                'mimetype': 'image/jpeg',
            })
            return att.id

        hero_id = upload_image('microsite_hero_image', 'hero')
        sec1_id = upload_image('microsite_sec1_image', 'sec1')
        sec2_id = upload_image('microsite_sec2_image', 'sec2')

        html_parts = []
        nombre_display = self.microsite_name or self.name or subdomain
        horario = self.microsite_horario or ''
        entrega = self.microsite_entrega or ''
        parking = self.microsite_parking or ''
        sec1_texto = self.microsite_sec1_texto or ''
        acerca1_texto = self.microsite_acerca1_texto or ''
        sec2_texto = self.microsite_acerca2_texto or ''
        sec1_titulo = self.microsite_acerca1_titulo or 'Sobre nosotros'
        sec2_titulo = self.microsite_acerca2_titulo or 'Nuestros servicios'
        button_text = self.microsite_button_text or 'Tienda'

        html_parts.append(website_builder.build_hero_section(nombre_display, hero_id, button_text).replace("/web/content/", "/web/image/ir.attachment/"))

        features = website_builder.build_features_section(horario, entrega, parking, subdomain)
        if features:
            html_parts.append(features)

        if sec1_texto:
            if sec1_id:
                html_parts.append(f'''<section class="s_kickoff o_cc o_cc5 o_colored_level pt104 pb120" data-snippet="s_kickoff" data-name="SEC1" style="background-image: url('/web/image/ir.attachment/{sec1_id}/datas'); background-size: cover; background-position: center; background-attachment: fixed; position: relative;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); z-index: 0;"></div>
    <div class="container" style="position: relative; z-index: 1;">
        <h2 class="h3-fs text-center text-white">{sec1_texto[:200]}</h2>
    </div>
</section>''')
            else:
                html_parts.append(f'''<section class="s_kickoff o_cc o_cc5 o_colored_level pt104 pb120" data-snippet="s_kickoff" data-name="SEC1" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); position: relative;">
    <div class="container" style="position: relative; z-index: 1;">
        <h2 class="h3-fs text-center text-white">{sec1_texto[:200]}</h2>
    </div>
</section>''')

        acerca = website_builder.build_acerca_section(acerca1_texto, sec2_texto, sec1_titulo, sec2_titulo, subdomain)
        if acerca:
            html_parts.append(acerca)

        separador_titulo = self.microsite_separador_titulo or 'Consume Productos Canarios'
        if sec2_id:
            html_parts.append(f'''<section class="s_kickoff o_cc o_cc5 pt104 pb120 o_colored_level" data-snippet="s_kickoff" data-name="Separador" style="background-image: url('/web/image/ir.attachment/{sec2_id}/datas'); background-size: cover; background-position: center; background-attachment: fixed; position: relative;">
    <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.4); z-index: 0;"></div>
    <div class="container" style="position: relative; z-index: 1;">
        <h2 class="h3-fs text-center text-white">{separador_titulo}</h2>
    </div>
</section>''')
        else:
            html_parts.append(f'''<section class="s_kickoff o_cc o_cc5 pt104 pb120 o_colored_level" data-snippet="s_kickoff" data-name="Separador" style="background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); position: relative;">
    <div class="container" style="position: relative; z-index: 1;">
        <h2 class="h3-fs text-center text-white">{separador_titulo}</h2>
    </div>
</section>''')

        html_parts.append(website_builder.build_cta_section())
        html_parts.append(website_builder.build_formulario_section(subdomain, map_url, company_info, self.microsite_website or '', self.microsite_phone2 or ''))
        html_parts.append(website_builder.build_subvenciones_section())

        # Aplicar logo y favicon al website (con sudo para usuarios no diseñadores)
        if self.microsite_logo:
            website.sudo().logo = self.microsite_logo
        if self.microsite_favicon:
            website.sudo().favicon = self.microsite_favicon
        # El footer lo gestiona el tema corporate_footer; no inyectamos uno manual

        html_content = '\n'.join(html_parts)
        full_arch = f'''<t name="Home - {subdomain}" t-name="{view_key}">
    <t t-call="website.layout">
        <div id="wrap" class="oe_structure oe_empty">
            {html_content}
        </div>
    </t>
</t>'''

        View = self.env['ir.ui.view'].sudo()
        Page = self.env['website.page'].sudo()
        view_ids = View.browse()
        # BUG-FIX v1.1-stable (legacy homepage lookup):
        # Algunos microsites antiguos usan claves legacy (ej. website.home-peluqueria-luna-y-mar)
        # en lugar del pattern website.homepage_<subdomain>. Si solo buscamos por key/name,
        # el sync cae en Corporate Homepage y deja el homepage real sin tocar.
        # 0. Buscar por la página homepage real del website (más fiable ante claves legacy)
        page = Page.search([
            ('website_id', '=', website.id),
            ('url', '=', '/'),
        ], limit=1)
        if page:
            view_ids = page.view_id
        # 1. Buscar por key exacto
        if not view_ids:
            view_ids = View.search([
                ('key', '=', view_key),
                ('website_id', '=', website.id),
            ], limit=1)
        # 2. Buscar por key legacy (pattern antiguo website.home-<subdomain>)
        if not view_ids:
            view_ids = View.search([
                ('key', 'ilike', f'website.home-{subdomain}%'),
                ('website_id', '=', website.id),
            ], limit=1)
        # 3. Buscar por name aproximado
        if not view_ids:
            view_ids = View.search([
                ('name', 'ilike', f'Home - {subdomain}'),
                ('website_id', '=', website.id),
            ], limit=1)
        # 4. Fallback a cualquier homepage
        if not view_ids:
            view_ids = View.search([
                ('website_id', '=', website.id),
                ('name', 'ilike', 'Home'),
            ], limit=1)

        if view_ids:
            view_ids.write({'arch_db': full_arch})
        else:
            View.create({
                'name': f'Home - {subdomain}',
                'key': view_key,
                'type': 'qweb',
                'arch_db': full_arch,
                'website_id': website.id,
            })

        self._update_theme_footer()
        self.microsite_last_sync = fields.Datetime.now()

    def _update_theme_footer(self):
        """Asegura que el footer del tema muestre website.name (nombre comercial)."""
        self.ensure_one()
        website = self.microsite_website_id
        if not website:
            return
        View = self.env['ir.ui.view'].sudo()
        footer_view = View.search([
            ('key', '=', 'theme_corporate_multi.corporate_footer'),
            ('website_id', '=', website.id),
        ], limit=1)
        if footer_view:
            new_arch = footer_view.arch_db.replace('t-field="res_company.name"', 't-field="website.name"')
            if new_arch != footer_view.arch_db:
                footer_view.write({'arch_db': new_arch})

    def write(self, vals):
        # Validación de formato de horario
        if 'microsite_horario' in vals:
            horario = vals['microsite_horario']
            if horario and str(horario).strip().lower() not in ['', 'nan', 'none', 'false']:
                parsed = website_builder.parse_horario_to_json(horario)
                if not parsed:
                    raise UserError("Formato de horario incorrecto. Use el formato: L-V 10:00-13:30 / L-V 16:30-20:00 / S 10:00-14:00")
                for dia, franjas in parsed.items():
                    if isinstance(franjas, list) and len(franjas) > 2:
                        raise UserError(f"El día {dia} tiene más de 2 franjas horarias. Máximo 2 franjas por día (mañana y tarde).")
        res = super(ResPartner, self).write(vals)
        if any(f in vals for f in MICROSITE_FIELDS):
            for partner in self:
                partner.invalidate_recordset(fnames=['has_microsite', 'microsite_website_id'])
                # Sincronizar RRSS del partner al website (con sudo) si cambiaron
                rrss_fields = ['microsite_facebook', 'microsite_instagram', 'microsite_twitter', 'microsite_linkedin', 'microsite_youtube']
                if any(f in vals for f in rrss_fields) and partner.microsite_website_id:
                    website_vals = {}
                    if 'microsite_facebook' in vals:
                        website_vals['social_facebook'] = vals['microsite_facebook']
                    if 'microsite_instagram' in vals:
                        website_vals['social_instagram'] = vals['microsite_instagram']
                    if 'microsite_twitter' in vals:
                        website_vals['social_twitter'] = vals['microsite_twitter']
                    if 'microsite_linkedin' in vals:
                        website_vals['social_linkedin'] = vals['microsite_linkedin']
                    if 'microsite_youtube' in vals:
                        website_vals['social_youtube'] = vals['microsite_youtube']
                    if website_vals:
                        partner.microsite_website_id.sudo().write(website_vals)
                # Sincronizar logo/favicon al website (con sudo) solo si se subió algo real
                if partner.microsite_website_id:
                    brand_vals = {}
                    if 'microsite_logo' in vals and vals['microsite_logo']:
                        brand_vals['logo'] = vals['microsite_logo']
                    if 'microsite_favicon' in vals and vals['microsite_favicon']:
                        brand_vals['favicon'] = vals['microsite_favicon']
                    if brand_vals:
                        partner.microsite_website_id.sudo().write(brand_vals)
                partner._sync_to_website()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        partners = super(ResPartner, self).create(vals_list)
        for partner in partners:
            if any(f in partner._cache or partner[f] for f in MICROSITE_FIELDS):
                partner._sync_to_website()
        return partners
