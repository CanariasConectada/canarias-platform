# -*- coding: utf-8 -*-
import re
from datetime import datetime
from odoo import models, fields, api

LOREM_PATTERNS = [
    re.compile(r'\blorem\b', re.IGNORECASE),
    re.compile(r'\bipsum\b', re.IGNORECASE),
]

# Fields that must not be empty for a "complete" microsite
REQUIRED_FIELDS = [
    'microsite_horario',
    'microsite_entrega',
    'microsite_parking',
    'microsite_sec1_texto',
    'microsite_acerca1_texto',
    'microsite_acerca2_texto',
    'microsite_phone',
    'microsite_email',
    'microsite_address',
]

# HTML sections that must exist in homepage arch_db
REQUIRED_SECTIONS = [
    ('Hero', 'data-name="Hero"'),
    ('Horario', 'data-name="Horario"'),
    ('Acerca', 'data-name="Acerca"'),
    ('Zona Comercial', 'data-name="Zona Comercial"'),
    ('Formulario', 'data-name="Formulario"'),
    ('Subvenciones', 'data-name="Subvenciones"'),
    ('Separador', 'data-name="Separador"'),
]

# Parent / protected website IDs (do not validate as microsites)
_PROTECTED_WS_IDS = {258, 259, 260, 262}


class MicrositeValidationReport(models.Model):
    _name = 'microsite.validation.report'
    _description = 'Microsite Validation Report'
    _order = 'create_date desc'

    name = fields.Char(string='Reporte', default=lambda self: f"Validación {fields.Datetime.now()}")
    date = fields.Datetime(string='Fecha', default=fields.Datetime.now)
    total_websites = fields.Integer(string='Total Microsites')
    ok_count = fields.Integer(string='OK')
    incomplete_count = fields.Integer(string='Incompletos')
    error_count = fields.Integer(string='Errores')
    line_ids = fields.One2many('microsite.validation.line', 'report_id', string='Detalles')

    def action_validate_all(self):
        """Run full validation across all microsites and store results."""
        self.ensure_one()
        self.line_ids.unlink()

        Website = self.env['website'].sudo()
        View = self.env['ir.ui.view'].sudo()
        Page = self.env['website.page'].sudo()

        websites = Website.search([])
        lines = []
        ok_count = 0
        incomplete_count = 0
        error_count = 0

        for ws in websites:
            if ws.id in _PROTECTED_WS_IDS:
                continue
            # Skip archived/orphan websites (no domain, inactive, or test domains)
            domain = ws.domain or ''
            if not domain or 'inactive-' in domain:
                continue

            company = ws.company_id
            partner = company.partner_id if company else None
            if not partner:
                continue

            # --- Field validation ---
            missing_fields = []
            for f in REQUIRED_FIELDS:
                val = getattr(partner, f, None)
                if not val or str(val).strip().lower() in ('', 'false', 'none', 'nan'):
                    missing_fields.append(f)

            # --- HTML section validation ---
            page = Page.search([('website_id', '=', ws.id), ('url', '=', '/')], limit=1)
            arch = ''
            if page and page.view_id:
                arch = page.view_id.arch_db or ''
            else:
                # fallback: search by key/name
                view = View.search([
                    ('website_id', '=', ws.id),
                    ('key', 'ilike', f'website.homepage_%'),
                ], limit=1)
                if not view:
                    view = View.search([
                        ('website_id', '=', ws.id),
                        ('name', 'ilike', 'Home'),
                    ], limit=1)
                if view:
                    arch = view.arch_db or ''

            missing_sections = []
            for sec_name, marker in REQUIRED_SECTIONS:
                if marker not in arch:
                    missing_sections.append(sec_name)

            # --- Lorem ipsum detection ---
            has_lorem = False
            lorem_snippets = []
            for pattern in LOREM_PATTERNS:
                for match in pattern.finditer(arch):
                    snippet = arch[max(0, match.start()-30):match.end()+30]
                    lorem_snippets.append(snippet)
                    has_lorem = True
            # Also check partner text fields
            for f in ['microsite_acerca1_texto', 'microsite_acerca2_texto', 'microsite_sec1_texto']:
                val = getattr(partner, f, '') or ''
                for pattern in LOREM_PATTERNS:
                    if pattern.search(val):
                        has_lorem = True
                        lorem_snippets.append(f"{f}: {val[:80]}...")

            # --- Determine state ---
            if missing_sections or has_lorem:
                state = 'error'
                error_count += 1
            elif missing_fields:
                state = 'incomplete'
                incomplete_count += 1
            else:
                state = 'ok'
                ok_count += 1

            lines.append((0, 0, {
                'website_id': ws.id,
                'partner_id': partner.id,
                'company_name': company.name or ws.name,
                'state': state,
                'missing_fields': ', '.join(missing_fields) if missing_fields else False,
                'missing_sections': ', '.join(missing_sections) if missing_sections else False,
                'has_lorem': has_lorem,
                'lorem_snippets': '\n'.join(lorem_snippets) if lorem_snippets else False,
            }))

        self.write({
            'line_ids': lines,
            'total_websites': len(lines),
            'ok_count': ok_count,
            'incomplete_count': incomplete_count,
            'error_count': error_count,
        })
        return True


class MicrositeValidationLine(models.Model):
    _name = 'microsite.validation.line'
    _description = 'Microsite Validation Line'

    report_id = fields.Many2one('microsite.validation.report', required=True, ondelete='cascade')
    website_id = fields.Many2one('website', string='Website', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Contacto', readonly=True)
    company_name = fields.Char(string='Compañía', readonly=True)
    state = fields.Selection([
        ('ok', 'OK'),
        ('incomplete', 'Incompleto'),
        ('error', 'Error'),
    ], string='Estado', readonly=True)
    missing_fields = fields.Text(string='Campos faltantes', readonly=True)
    missing_sections = fields.Text(string='Secciones faltantes', readonly=True)
    has_lorem = fields.Boolean(string='Tiene Lorem Ipsum', readonly=True)
    lorem_snippets = fields.Text(string='Fragmentos Lorem', readonly=True)

    def action_open_partner(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'res.partner',
            'res_id': self.partner_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
