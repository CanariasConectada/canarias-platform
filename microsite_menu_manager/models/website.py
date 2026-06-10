from odoo import models


class Website(models.Model):
    _inherit = 'website'

    def get_menu_profile(self):
        """
        Determina el perfil de menú según el tipo de website.
        
        Returns:
            'canarias'  -> Canarias Conectada (padre)
            'zone'      -> Zona Comercial (Guanarteme, Tamaraceite, Lomo Los Frailes)
            'microsite' -> Microsite individual
        """
        self.ensure_one()
        domain = (self.domain or '').lower()
        if domain == 'https://canariasconectada.es' or domain == 'http://canariasconectada.es':
            return 'canarias'
        if self.zone_id:
            return 'zone'
        return 'microsite'

    def get_reviews_partner(self):
        """
        Devuelve el res.partner cuyo flag enable_reviews controla
        si se muestra el menú de Reseñas para este website.
        
        - Canarias Conectada / Zonas: partner de la compañía principal
        - Microsite: partner vinculado al website (por website_id, domain o compañía)
        """
        self.ensure_one()
        profile = self.get_menu_profile()
        if profile in ('canarias', 'zone'):
            # Usar el partner de la compañía del website
            if self.company_id and self.company_id.partner_id:
                return self.company_id.partner_id
            return self.env['res.partner']
        # Microsite: buscar partner que tenga este website
        partner = self.env['res.partner'].sudo().search([
            ('website_id', '=', self.id),
        ], limit=1)
        if not partner:
            # Fallback: buscar por dominio del website en el campo website (char)
            domain = (self.domain or '').replace('https://', '').replace('http://', '').rstrip('/')
            if domain:
                partner = self.env['res.partner'].sudo().search([
                    ('website', 'ilike', domain),
                ], limit=1)
        if not partner and self.company_id and self.company_id.partner_id:
            partner = self.company_id.partner_id
        return partner
