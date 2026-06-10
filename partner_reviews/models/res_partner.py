# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    enable_reviews = fields.Boolean(
        string='Habilitar página de reseñas',
        default=False,
        help='Si está activado, se habilitará una página de reseñas para este negocio en su microsite'
    )
    review_rating_ids = fields.One2many(
        'partner.review.rating',
        'partner_id',
        string='Valoraciones'
    )
    review_comment_ids = fields.One2many(
        'partner.review.comment',
        'partner_id',
        string='Comentarios'
    )
    review_rating_avg = fields.Float(
        string='Valoración Promedio',
        compute='_compute_review_stats',
        store=True,
        digits=(2, 1)
    )
    review_rating_count = fields.Integer(
        string='Total Valoraciones',
        compute='_compute_review_stats',
        store=True
    )
    review_comment_count = fields.Integer(
        string='Total Comentarios',
        compute='_compute_review_comment_count',
        store=True
    )

    @api.depends('review_rating_ids', 'review_rating_ids.rating')
    def _compute_review_stats(self):
        for partner in self:
            ratings = partner.review_rating_ids.mapped('rating')
            if ratings:
                partner.review_rating_avg = sum(ratings) / len(ratings)
                partner.review_rating_count = len(ratings)
            else:
                partner.review_rating_avg = 0
                partner.review_rating_count = 0

    @api.depends('review_comment_ids', 'review_comment_ids.estado')
    def _compute_review_comment_count(self):
        for partner in self:
            partner.review_comment_count = self.env['partner.review.comment'].search_count([
                ('partner_id', '=', partner.id),
                ('estado', '=', 'aprobado'),
                ('parent_id', '=', False)
            ])

    # ========================================
    # MENÚ DINÁMICO DE WEBSITE
    # ========================================
    def _create_reviews_menu(self):
        """Crea el menú de reseñas en el website asociado al partner"""
        self.ensure_one()
        if not self.microsite_website_id:
            return
        website = self.microsite_website_id
        Menu = self.env['website.menu'].sudo()

        existing = Menu.search([
            ('website_id', '=', website.id),
            ('url', '=', '/resenas'),
        ], limit=1)
        if existing:
            return

        Menu.create({
            'name': 'Reseñas',
            'url': '/resenas',
            'website_id': website.id,
            'parent_id': website.menu_id.id,
            'sequence': 50,
        })

    def _remove_reviews_menu(self):
        """Elimina el menú de reseñas del website asociado al partner"""
        self.ensure_one()
        if not self.microsite_website_id:
            return
        website = self.microsite_website_id
        Menu = self.env['website.menu'].sudo()
        menus = Menu.search([
            ('website_id', '=', website.id),
            ('url', '=', '/resenas'),
        ])
        if menus:
            try:
                menus.unlink()
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    "No se pudo eliminar el menú de reseñas del website %s: %s", website.name, str(e)
                )

    def _update_reviews_menu_backend(self):
        """Activa o desactiva el menú backend 'Reseñas' según haya comercios con reviews habilitadas."""
        menu = self.env.ref('partner_reviews.menu_partner_reviews_root', raise_if_not_found=False)
        if not menu:
            return
        has_active_reviews = self.env['res.company'].search_count([
            ('partner_id.enable_reviews', '=', True)
        ]) > 0
        menu.sudo().write({'active': has_active_reviews})

    def write(self, vals):
        result = super(ResPartner, self).write(vals)
        if 'enable_reviews' in vals:
            for partner in self:
                if partner.enable_reviews:
                    partner._create_reviews_menu()
                else:
                    partner._remove_reviews_menu()
            self._update_reviews_menu_backend()
        return result

    # ========================================
    # UTILIDAD: ¿ES USUARIO DE ESTE PARTNER?
    # ========================================
    def es_usuario_del_partner(self, user):
        """Devuelve True si el usuario dado está vinculado a este partner."""
        self.ensure_one()
        if not user:
            return False
        return user.id in self.user_ids.ids
