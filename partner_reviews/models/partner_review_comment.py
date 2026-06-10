# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import html_escape


class PartnerReviewComment(models.Model):
    _name = 'partner.review.comment'
    _description = 'Comentario de Reseña'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Comercio',
        required=True,
        ondelete='cascade',
        index=True,
    )
    parent_id = fields.Many2one(
        'partner.review.comment',
        string='Comentario padre',
        ondelete='cascade',
        index=True,
        help='Para respuestas anidadas (1 nivel)'
    )
    respuesta_ids = fields.One2many(
        'partner.review.comment',
        'parent_id',
        string='Respuestas',
        domain=[('estado', '=', 'aprobado')]
    )
    autor_id = fields.Many2one(
        'res.users',
        string='Autor',
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    autor_nombre = fields.Char(
        string='Nombre del autor',
        related='autor_id.name',
        store=True
    )
    autor_imagen = fields.Binary(
        string='Avatar del autor',
        related='autor_id.avatar_128',
        store=False
    )
    autor_imagen_url = fields.Char(
        string='URL Avatar',
        compute='_compute_autor_imagen_url',
        store=False
    )
    contenido = fields.Text(string='Comentario', required=True)
    contenido_resumido = fields.Char(
        string='Vista previa',
        compute='_compute_contenido_resumido',
        store=True
    )
    estado = fields.Selection([
        ('pendiente', 'Pendiente de moderación'),
        ('aprobado', 'Aprobado'),
        ('rechazado', 'Rechazado')
    ], string='Estado', default='pendiente', required=True, tracking=True)
    contiene_palabras_prohibidas = fields.Boolean(
        string='Contiene palabras prohibidas',
        default=False
    )
    es_respuesta = fields.Boolean(
        string='Es respuesta',
        compute='_compute_es_respuesta',
        store=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        related='partner_id.company_id',
        store=True,
        index=True,
    )

    @api.depends('contenido')
    def _compute_contenido_resumido(self):
        for comentario in self:
            if comentario.contenido:
                resumen = comentario.contenido[:100]
                if len(comentario.contenido) > 100:
                    resumen += '...'
                comentario.contenido_resumido = resumen
            else:
                comentario.contenido_resumido = ''

    @api.depends('parent_id')
    def _compute_es_respuesta(self):
        for comentario in self:
            comentario.es_respuesta = bool(comentario.parent_id)

    def _compute_autor_imagen_url(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        # Forzar https para evitar Mixed Content
        base_url = base_url.replace('http://', 'https://')
        for comentario in self:
            if comentario.autor_id:
                comentario.autor_imagen_url = f"{base_url}/web/image/res.users/{comentario.autor_id.id}/avatar_128"
            else:
                comentario.autor_imagen_url = "/web/static/img/user_placeholder.jpg"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            contenido = vals.get('contenido', '')
            palabras_prohibidas = self.env['partner.review.palabra.prohibida'].search([
                ('active', '=', True)
            ])
            tiene_palabras_prohibidas = False
            contenido_lower = contenido.lower()
            for palabra in palabras_prohibidas:
                if palabra.name.lower() in contenido_lower:
                    tiene_palabras_prohibidas = True
                    break
            if tiene_palabras_prohibidas:
                vals['contiene_palabras_prohibidas'] = True
                vals['estado'] = 'pendiente'
            else:
                vals['estado'] = 'aprobado'
        comentarios = super(PartnerReviewComment, self).create(vals_list)
        for comentario in comentarios:
            if comentario.contiene_palabras_prohibidas:
                comentario._notificar_moderacion()
            comentario._notificar_partner()
        return comentarios

    def _notificar_moderacion(self):
        self.ensure_one()
        try:
            grupo_moderadores = self.env.ref('partner_reviews.group_partner_reviews_moderator', raise_if_not_found=False)
            if not grupo_moderadores:
                return
            usuarios_moderadores = self.env['res.users'].search([('groups_id', 'in', grupo_moderadores.id)])
        except Exception:
            return
        if not usuarios_moderadores:
            return
        for usuario in usuarios_moderadores:
            self.env['mail.activity'].create({
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': _('Nuevo comentario pendiente de moderación'),
                'note': _('El comentario de %s contiene palabras que requieren revisión.') % self.autor_nombre,
                'user_id': usuario.id,
                'res_id': self.id,
                'res_model_id': self.env['ir.model']._get_id('partner.review.comment'),
            })
        template = self.env.ref('partner_reviews.email_template_comentario_moderacion', raise_if_not_found=False)
        if template:
            for usuario in usuarios_moderadores:
                if usuario.email:
                    template.with_context(
                        destinatario=usuario,
                        comentario=self
                    ).send_mail(self.id, force_send=True, email_values={'email_to': usuario.email})

    def _notificar_partner(self):
        """Envía un email al partner cuando recibe un nuevo comentario o respuesta."""
        self.ensure_one()
        partner = self.partner_id
        if not partner or not partner.email:
            return
        tipo = 'respuesta' if self.parent_id else 'comentario'
        subject = f"Nueva {tipo} en {partner.name}"
        body = f"""
        <p>Hola <strong>{html_escape(partner.name)}</strong>,</p>
        <p>Has recibido una nueva {tipo} en tu página de reseñas:</p>
        <div style="background:#f8f9fa;padding:15px;border-radius:5px;margin:15px 0;">
            <p><strong>Autor:</strong> {html_escape(self.autor_nombre)}</p>
            <p><strong>Contenido:</strong></p>
            <p style="font-style:italic;">{html_escape(self.contenido)}</p>
        </div>
        <p>Puedes gestionar tus reseñas desde el panel de administración.</p>
        """
        mail = self.env['mail.mail'].sudo().create({
            'subject': subject,
            'body_html': body,
            'email_to': partner.email,
            'auto_delete': True,
        })
        mail.send()

    def action_aprobar(self):
        self.write({'estado': 'aprobado'})

    def action_rechazar(self):
        self.write({'estado': 'rechazado'})

    def action_eliminar(self):
        """Elimina el comentario y desvincula sus respuestas."""
        for comentario in self:
            # Desvincular respuestas antes de eliminar
            if comentario.respuesta_ids:
                comentario.respuesta_ids.write({'parent_id': False})
            comentario.unlink()

    @api.model
    def get_comentarios_aprobados(self, partner_id, offset=0, limit=10):
        comentarios = self.search([
            ('partner_id', '=', partner_id),
            ('estado', '=', 'aprobado'),
            ('parent_id', '=', False)
        ], order='create_date desc', offset=offset, limit=limit)
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        # Forzar https para evitar Mixed Content
        base_url = base_url.replace('http://', 'https://')
        resultado = []
        for comentario in comentarios:
            data = {
                'id': comentario.id,
                'autor_id': comentario.autor_id.id,
                'autor_nombre': comentario.autor_nombre,
                'autor_imagen_url': comentario.autor_imagen_url,
                'contenido': comentario.contenido,
                'fecha': comentario.create_date.strftime('%d/%m/%Y %H:%M'),
                'respuestas': []
            }
            for respuesta in comentario.respuesta_ids.filtered(lambda r: r.estado == 'aprobado'):
                resp_url = f"{base_url}/web/image/res.users/{respuesta.autor_id.id}/avatar_128" if respuesta.autor_id else "/web/static/img/user_placeholder.jpg"
                data['respuestas'].append({
                    'id': respuesta.id,
                    'autor_id': respuesta.autor_id.id,
                    'autor_nombre': respuesta.autor_nombre,
                    'autor_imagen_url': resp_url,
                    'contenido': respuesta.contenido,
                    'fecha': respuesta.create_date.strftime('%d/%m/%Y %H:%M'),
                })
            resultado.append(data)
        return resultado

    @api.constrains('parent_id')
    def _check_nivel_anidacion(self):
        for comentario in self:
            if comentario.parent_id and comentario.parent_id.parent_id:
                raise UserError(_('No se permiten respuestas anidadas de más de 1 nivel.'))
