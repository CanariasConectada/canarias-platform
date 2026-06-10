# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.tools import html_escape


class PartnerReviewRating(models.Model):
    _name = 'partner.review.rating'
    _description = 'Valoración de Comercio'
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Comercio',
        required=True,
        ondelete='cascade',
        index=True,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        required=True,
        ondelete='cascade',
        index=True,
        default=lambda self: self.env.user,
    )
    rating = fields.Integer(
        string='Estrellas',
        required=True,
        help='Valoración de 1 a 5 estrellas'
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='partner_id.company_id',
        store=True,
        index=True,
    )

    _unique_user_partner = models.Constraint(
        'unique(partner_id, user_id)',
        'Ya has valorado este comercio. Solo puedes valorar una vez.'
    )

    @api.constrains('rating')
    def _check_rating_range(self):
        for record in self:
            if record.rating < 1 or record.rating > 5:
                raise ValidationError(
                    'La valoración debe estar entre 1 y 5 estrellas.'
                )

    def _notificar_partner(self):
        """Envía un email al partner cuando recibe una nueva valoración."""
        self.ensure_one()
        partner = self.partner_id
        if not partner or not partner.email:
            return
        subject = f"Nueva valoración en {partner.name}"
        body = f"""
        <p>Hola <strong>{escapeHtml(partner.name)}</strong>,</p>
        <p>Has recibido una nueva valoración en tu página de reseñas:</p>
        <div style="background:#f8f9fa;padding:15px;border-radius:5px;margin:15px 0;">
            <p><strong>Valoración:</strong> {self.rating} de 5 estrellas</p>
            <p><strong>Usuario:</strong> {escapeHtml(self.user_id.name)}</p>
        </div>
        <p>Puedes ver todas tus reseñas en el panel de administración.</p>
        """
        mail = self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': partner.email,
            'auto_delete': True,
        })
        mail.send()


