# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import re


class MemoriaVivaComentario(models.Model):
    _name = 'memoria.viva.comentario'
    _description = 'Comentario - Memoria Viva'
    _inherit = ['mail.thread']
    _order = 'create_date desc'

    lugar_id = fields.Many2one(
        'memoria.viva.historia',
        string='Lugar',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    parent_id = fields.Many2one(
        'memoria.viva.comentario',
        string='Comentario padre',
        ondelete='cascade',
        index=True,
        help='Para respuestas anidadas (1 nivel)'
    )
    
    respuesta_ids = fields.One2many(
        'memoria.viva.comentario',
        'parent_id',
        string='Respuestas',
        domain=[('estado', '=', 'aprobado')]
    )
    
    autor_id = fields.Many2one(
        'res.users',
        string='Autor',
        required=True,
        default=lambda self: self.env.user,
        index=True
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
    
    @api.depends('contenido')
    def _compute_contenido_resumido(self):
        for comentario in self:
            if comentario.contenido:
                # Primeros 100 caracteres
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
        """Genera URL del avatar del autor"""
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        for comentario in self:
            if comentario.autor_id:
                comentario.autor_imagen_url = f"{base_url}/web/image/res.users/{comentario.autor_id.id}/avatar_128"
            else:
                comentario.autor_imagen_url = "/web/static/img/user_placeholder.jpg"
    
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Verificar palabras prohibidas
            contenido = vals.get('contenido', '')
            palabras_prohibidas = self.env['memoria.viva.palabra.prohibida'].search([
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
        
        comentarios = super(MemoriaVivaComentario, self).create(vals_list)
        
        # Notificar si hay comentarios pendientes
        for comentario in comentarios:
            if comentario.contiene_palabras_prohibidas:
                comentario._notificar_moderacion()
        
        return comentarios
    
    def _notificar_moderacion(self):
        """Crea activity y envía email a moderadores"""
        self.ensure_one()
        
        # Buscar grupo de aprobadores
        try:
            grupo_aprobadores = self.env.ref('memoria_viva.group_memoria_viva_approver', raise_if_not_found=False)
            if not grupo_aprobadores:
                return
            usuarios_aprobadores = self.env['res.users'].search([('groups_id', 'in', grupo_aprobadores.id)])
        except Exception:
            return
        
        if not usuarios_aprobadores:
            return
        
        # Crear activity para cada aprobador
        for usuario in usuarios_aprobadores:
            self.env['mail.activity'].create({
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': _('Nuevo comentario pendiente de moderación'),
                'note': _('El comentario de %s contiene palabras que requieren revisión.') % self.autor_nombre,
                'user_id': usuario.id,
                'res_id': self.id,
                'res_model_id': self.env['ir.model']._get_id('memoria.viva.comentario'),
            })
        
        # Enviar email
        template = self.env.ref('memoria_viva.email_template_comentario_moderacion', raise_if_not_found=False)
        if template:
            for usuario in usuarios_aprobadores:
                if usuario.email:
                    template.with_context(
                        destinatario=usuario,
                        comentario=self
                    ).send_mail(self.id, force_send=True, email_values={'email_to': usuario.email})
    
    def action_aprobar(self):
        self.write({'estado': 'aprobado'})
    
    def action_rechazar(self):
        self.write({'estado': 'rechazado'})
    
    @api.model
    def get_comentarios_aprobados(self, lugar_id, offset=0, limit=10):
        """Retorna comentarios aprobados para el frontend"""
        comentarios = self.search([
            ('lugar_id', '=', lugar_id),
            ('estado', '=', 'aprobado'),
            ('parent_id', '=', False)  # Solo comentarios principales
        ], order='create_date desc', offset=offset, limit=limit)
        
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
        resultado = []
        for comentario in comentarios:
            data = {
                'id': comentario.id,
                'autor_nombre': comentario.autor_nombre,
                'autor_imagen_url': comentario.autor_imagen_url,
                'contenido': comentario.contenido,
                'fecha': comentario.create_date.strftime('%d/%m/%Y %H:%M'),
                'respuestas': []
            }
            # Incluir respuestas aprobadas (1 nivel)
            for respuesta in comentario.respuesta_ids.filtered(lambda r: r.estado == 'aprobado'):
                resp_url = f"{base_url}/web/image/res.users/{respuesta.autor_id.id}/avatar_128" if respuesta.autor_id else "/web/static/img/user_placeholder.jpg"
                data['respuestas'].append({
                    'id': respuesta.id,
                    'autor_nombre': respuesta.autor_nombre,
                    'autor_imagen_url': resp_url,
                    'contenido': respuesta.contenido,
                    'fecha': respuesta.create_date.strftime('%d/%m/%Y %H:%M'),
                })
            resultado.append(data)
        
        return resultado
    
    @api.constrains('parent_id')
    def _check_nivel_anidacion(self):
        """Valida que solo haya 1 nivel de anidación"""
        for comentario in self:
            if comentario.parent_id and comentario.parent_id.parent_id:
                raise UserError(_('No se permiten respuestas anidadas de más de 1 nivel.'))
