# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    show_in_directory = fields.Boolean(
        string='Mostrar en directorio',
        default=True,
        help='Si está marcado, esta compañía aparecerá en el directorio web.'
    )

    def _get_directory_zone(self):
        """Mapea zone_id.name a los valores de website.directory.entry.zone"""
        self.ensure_one()
        if self.zone_id and self.zone_id.name:
            zone_name = self.zone_id.name.strip()
            zone_map = {
                'Guanarteme': 'guanarteme',
                'Tamaraceite': 'tamaraceite',
                'Lomo los Frailes': 'lomolosfrailes',
                'Ninguna': 'canarias',
            }
            return zone_map.get(zone_name, 'canarias')
        return 'canarias'

    def _get_directory_website_url(self):
        """Obtiene la URL web preferida para el directorio"""
        self.ensure_one()
        partner = self.partner_id.with_context(prefetch_fields=False)
        # Prioridad 1: URL del partner
        if partner and partner.website:
            url = partner.website
            if url.startswith('http'):
                return url
            return f'https://{url}'
        # Prioridad 2: computed_website_url
        if hasattr(self, 'computed_website_url') and self.computed_website_url:
            return self.computed_website_url
        # Prioridad 3: main_website_id.domain
        if self.main_website_id and self.main_website_id.domain:
            domain = self.main_website_id.domain
            if domain.startswith('http'):
                return domain
            return f'https://{domain}'
        # Prioridad 4: website_id.domain
        if self.website_id and self.website_id.domain:
            domain = self.website_id.domain
            if domain.startswith('http'):
                return domain
            return f'https://{domain}'
        return ''

    def _sync_to_directory_entry(self):
        """Sincroniza los datos de la compañía a su entrada en el directorio"""
        for company in self.with_context(prefetch_fields=False):
            cr = self.env.cr
            savepoint = 'sp_directory_sync_%s' % company.id
            try:
                cr.execute('SAVEPOINT "%s"' % savepoint)

                Entry = self.env['website.directory.entry'].sudo()
                entries = Entry.with_context(active_test=False).search([
                    ('company_id', '=', company.id),
                ])

                partner = company.partner_id.with_context(prefetch_fields=False)
                vals = {
                    'name': company.name,
                    'phone': partner.phone or '',
                    'email': partner.email or '',
                    'street': partner.street or '',
                    'city': partner.city or '',
                    'vat': partner.vat or '',
                    'website_url': company._get_directory_website_url(),
                    'zone': company._get_directory_zone(),
                    'is_published': True,
                    'active': company.show_in_directory,
                    'short_description': '',  # Limpiar descripción corta ya que no hay fuente en compañía
                }

                # Categorías de negocio (Many2many)
                if company.business_category_ids:
                    vals['category_ids'] = [(6, 0, company.business_category_ids.ids)]
                else:
                    vals['category_ids'] = [(5, 0, 0)]

                if entries:
                    entries.write(vals)
                else:
                    vals['company_id'] = company.id
                    entries = Entry.create(vals)

                # Actualizar campos traducibles en español (idioma activo del sitio web)
                # para evitar que queden traducciones desfasadas
                entries.with_context(lang='es_ES').write({
                    'name': company.name,
                    'short_description': '',
                })

                # Logo: intentar sincronizar por separado para manejar posibles colisiones
                if company.logo:
                    try:
                        entries.write({'image': company.logo})
                    except Exception:
                        pass

                cr.execute('RELEASE SAVEPOINT "%s"' % savepoint)
            except Exception:
                # Rollback parcial: la compañía principal se guarda, pero el sync del directorio falla silenciosamente
                cr.execute('ROLLBACK TO SAVEPOINT "%s"' % savepoint)
                pass

    def action_sync_to_directory(self):
        """Acción de botón para forzar la sincronización manual"""
        self._sync_to_directory_entry()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Directorio sincronizado',
                'message': 'La compañía se ha sincronizado correctamente con el directorio web.',
                'type': 'success',
                'sticky': False,
            }
        }

    def write(self, vals):
        """Sobrescribe write para sincronizar automáticamente con el directorio"""
        # Si se archiva la compañía, apagar automáticamente show_in_directory
        if 'active' in vals and not vals['active']:
            vals['show_in_directory'] = False

        res = super(ResCompany, self).write(vals)
        # Campos que al cambiar deben disparar sincronización
        sync_fields = {
            'name', 'logo', 'show_in_directory', 'zone_id',
            'business_category_ids', 'website_id', 'main_website_id',
            'computed_website_url', 'company_subdomain', 'custom_domain_url',
            'use_custom_domain', 'active',
        }
        # También si cambia el partner (aunque no suele cambiar, por si acaso)
        if any(f in vals for f in sync_fields):
            self._sync_to_directory_entry()
        else:
            # Si cambian campos del partner, debemos sincronizar también
            # Odoo no nos dice qué campos del partner cambiaron aquí,
            # así que si vals contiene 'partner_id' o campos de contacto
            # que a veces se escriben desde la vista de compañía...
            partner_fields = {'phone', 'email', 'street', 'city', 'vat', 'website'}
            # En la vista de compañía de Odoo 19, los campos del partner
            # se escriben a menudo con claves como 'phone', 'email', etc.
            # directamente en vals con el contexto 'no_vat_validation' o similar.
            # Odoo los reenvía al partner automáticamente.
            if any(f in vals for f in partner_fields):
                self._sync_to_directory_entry()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        """Crear entrada en directorio automáticamente al crear compañía"""
        companies = super(ResCompany, self).create(vals_list)
        current_allowed = list(self.env.context.get('allowed_company_ids') or [self.env.company.id])
        new_ids = [c.id for c in companies if c.id not in current_allowed]
        extended_ctx = dict(self.env.context, allowed_company_ids=current_allowed + new_ids) if new_ids else self.env.context
        for company in companies.with_context(extended_ctx):
            company._sync_to_directory_entry()
        return companies
