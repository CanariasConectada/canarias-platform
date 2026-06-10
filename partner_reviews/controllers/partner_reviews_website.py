# -*- coding: utf-8 -*-
import werkzeug
from odoo import http
from odoo.http import request
import json


class PartnerReviewsWebsite(http.Controller):
    """Controlador Website para Reseñas de Comercios"""

    def _get_partner_by_website(self):
        """Busca el partner (comercio) asociado al website actual"""
        website = request.website
        if not website:
            return None
        # Buscar la company asociada a este website
        company = request.env['res.company'].sudo().search([
            ('website_id', '=', website.id)
        ], limit=1)
        if company and company.partner_id and company.partner_id.enable_reviews:
            return company.partner_id
        return None

    # ========================================
    # PÁGINA DE RESEÑAS
    # ========================================
    @http.route('/resenas', auth='public', website=True)
    def reviews_page(self, **kw):
        """Página de reseñas del comercio - detecta website desde request"""
        partner = self._get_partner_by_website()
        if not partner:
            raise werkzeug.exceptions.NotFound()

        Settings = request.env['partner.review.settings'].sudo().get_settings()
        config = {
            'permitir_comentarios': Settings.permitir_comentarios,
        }

        # Calcular distribución de estrellas
        ratings = request.env['partner.review.rating'].sudo().search([
            ('partner_id', '=', partner.id)
        ])
        distribucion = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        for r in ratings:
            if r.rating in distribucion:
                distribucion[r.rating] += 1

        return request.render('partner_reviews.reviews_page_template', {
            'partner': partner,
            'config': config,
            'distribucion': distribucion,
            'total_ratings': len(ratings),
        })

    # ========================================
    # VALORACIONES (RATINGS)
    # ========================================
    @http.route('/partner-reviews/rating/enviar', auth='user', type='http', csrf=False, methods=['POST'])
    def enviar_rating(self, **kw):
        import json as json_mod
        headers = {'Content-Type': 'application/json'}
        try:
            data = json_mod.loads(request.httprequest.data) if request.httprequest.data else {}
            partner_id = data.get('partner_id')
            rating = data.get('rating')
            if not partner_id:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no especificado'}), headers=headers)
            if not rating or not isinstance(rating, int) or rating < 1 or rating > 5:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'La valoración debe ser un número entre 1 y 5'}), headers=headers)

            Partner = request.env['res.partner'].sudo()
            partner = Partner.browse(int(partner_id))
            if not partner.exists() or not partner.enable_reviews:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no encontrado'}), headers=headers)

            Rating = request.env['partner.review.rating'].sudo()
            existing = Rating.search([
                ('partner_id', '=', int(partner_id)),
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            if existing:
                existing.write({'rating': rating})
                mensaje = 'Tu valoración ha sido actualizada.'
            else:
                rating_obj = Rating.create({
                    'partner_id': int(partner_id),
                    'user_id': request.env.user.id,
                    'rating': rating
                })
                rating_obj._notificar_partner()
                mensaje = '¡Gracias por valorar este comercio!'

            partner.invalidate_recordset()
            return request.make_response(json_mod.dumps({
                'success': True,
                'mensaje': mensaje,
                'rating_avg': partner.review_rating_avg,
                'rating_count': partner.review_rating_count,
                'user_rating': rating
            }), headers=headers)
        except Exception as e:
            return request.make_response(json_mod.dumps({'success': False, 'error': str(e)}), headers=headers)

    @http.route('/partner-reviews/rating/eliminar', auth='user', type='http', csrf=False, methods=['POST'])
    def eliminar_rating(self, **kw):
        import json as json_mod
        headers = {'Content-Type': 'application/json'}
        try:
            data = json_mod.loads(request.httprequest.data) if request.httprequest.data else {}
            partner_id = data.get('partner_id')
            if not partner_id:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no especificado'}), headers=headers)

            Rating = request.env['partner.review.rating'].sudo()
            existing = Rating.search([
                ('partner_id', '=', int(partner_id)),
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            if existing:
                existing.unlink()
                Partner = request.env['res.partner'].sudo()
                partner = Partner.browse(int(partner_id))
                partner.invalidate_recordset()
                return request.make_response(json_mod.dumps({
                    'success': True,
                    'mensaje': 'Tu valoración ha sido eliminada.',
                    'rating_avg': partner.review_rating_avg,
                    'rating_count': partner.review_rating_count,
                    'user_rating': 0
                }), headers=headers)
            else:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'No tienes una valoración para este comercio'}), headers=headers)
        except Exception as e:
            return request.make_response(json_mod.dumps({'success': False, 'error': str(e)}), headers=headers)

    @http.route('/partner-reviews/rating/mi-valoracion', auth='user', type='http', methods=['GET'])
    def mi_valoracion(self, partner_id, **kw):
        import json as json_mod
        headers = {'Content-Type': 'application/json'}
        try:
            if not partner_id:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no especificado'}), headers=headers)
            Rating = request.env['partner.review.rating'].sudo()
            rating = Rating.search([
                ('partner_id', '=', int(partner_id)),
                ('user_id', '=', request.env.user.id)
            ], limit=1)
            return request.make_response(json_mod.dumps({
                'success': True,
                'rating': rating.rating if rating else 0
            }), headers=headers)
        except Exception as e:
            return request.make_response(json_mod.dumps({'success': False, 'error': str(e)}), headers=headers)

    # ========================================
    # COMENTARIOS
    # ========================================
    @http.route('/partner-reviews/comment/enviar', auth='user', type='http', csrf=False, methods=['POST'])
    def enviar_comentario(self, **kw):
        import json as json_mod
        headers = {'Content-Type': 'application/json'}
        try:
            data = json_mod.loads(request.httprequest.data) if request.httprequest.data else {}
            partner_id = data.get('partner_id')
            contenido = data.get('contenido', '').strip()
            parent_id = data.get('parent_id') or None
            if not partner_id:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no especificado'}), headers=headers)
            if not contenido:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'El comentario está vacío'}), headers=headers)

            Partner = request.env['res.partner'].sudo()
            partner = Partner.browse(int(partner_id))
            if not partner.exists() or not partner.enable_reviews:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no encontrado'}), headers=headers)

            Settings = request.env['partner.review.settings'].sudo().get_settings()
            if not Settings.permitir_comentarios:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Los comentarios están deshabilitados'}), headers=headers)

            Comentario = request.env['partner.review.comment'].sudo()
            vals = {
                'partner_id': int(partner_id),
                'autor_id': request.env.user.id,
                'contenido': contenido,
            }
            if parent_id:
                vals['parent_id'] = int(parent_id)
            comentario = Comentario.create(vals)

            result = {
                'success': True,
                'comentario': {
                    'id': comentario.id,
                    'autor_nombre': comentario.autor_nombre,
                    'autor_imagen_url': comentario.autor_imagen_url,
                    'contenido': comentario.contenido,
                    'fecha': comentario.create_date.strftime('%d/%m/%Y %H:%M'),
                    'estado': comentario.estado,
                    'pendiente_moderacion': comentario.contiene_palabras_prohibidas,
                }
            }
            if comentario.contiene_palabras_prohibidas:
                result['mensaje'] = 'Tu comentario está pendiente de moderación y será revisado por un administrador.'
            return request.make_response(json_mod.dumps(result), headers=headers)
        except Exception as e:
            return request.make_response(json_mod.dumps({'success': False, 'error': str(e)}), headers=headers)

    @http.route('/partner-reviews/comment/eliminar', auth='user', type='http', csrf=False, methods=['POST'])
    def eliminar_comentario(self, **kw):
        import json as json_mod
        headers = {'Content-Type': 'application/json'}
        try:
            data = json_mod.loads(request.httprequest.data) if request.httprequest.data else {}
            comment_id = data.get('comment_id')
            if not comment_id:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comentario no especificado'}), headers=headers)

            Comentario = request.env['partner.review.comment'].sudo()
            comentario = Comentario.browse(int(comment_id))
            if not comentario.exists():
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comentario no encontrado'}), headers=headers)

            user = request.env.user
            es_autor = comentario.autor_id.id == user.id
            es_moderador = user.has_group('partner_reviews.group_partner_reviews_manager')
            es_empleado_partner = bool(comentario.partner_id.user_ids and user.id in comentario.partner_id.user_ids.ids)

            if not (es_autor or es_moderador or es_empleado_partner):
                return request.make_response(json_mod.dumps({'success': False, 'error': 'No tienes permiso para eliminar este comentario'}), headers=headers)

            comentario.action_eliminar()
            return request.make_response(json_mod.dumps({'success': True, 'mensaje': 'Comentario eliminado.'}), headers=headers)
        except Exception as e:
            return request.make_response(json_mod.dumps({'success': False, 'error': str(e)}), headers=headers)

    @http.route('/partner-reviews/comment/listar', auth='public', type='http', methods=['GET'])
    def listar_comentarios(self, partner_id, offset=0, limit=10, **kw):
        import json as json_mod
        headers = {'Content-Type': 'application/json'}
        try:
            if not partner_id:
                return request.make_response(json_mod.dumps({'success': False, 'error': 'Comercio no especificado'}), headers=headers)

            Comentario = request.env['partner.review.comment'].sudo()
            comentarios = Comentario.get_comentarios_aprobados(
                int(partner_id),
                offset=int(offset),
                limit=int(limit)
            )
            total = Comentario.search_count([
                ('partner_id', '=', int(partner_id)),
                ('estado', '=', 'aprobado'),
                ('parent_id', '=', False)
            ])
            return request.make_response(json_mod.dumps({
                'success': True,
                'comentarios': comentarios,
                'total': total,
                'tiene_mas': total > (int(offset) + int(limit))
            }), headers=headers)
        except Exception as e:
            return request.make_response(json_mod.dumps({'success': False, 'error': str(e)}), headers=headers)
