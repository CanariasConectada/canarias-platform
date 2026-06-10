/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

publicWidget.registry.PartnerReviews = publicWidget.Widget.extend({
    selector: '#partner-reviews-app',
    events: {
        'click .partner-review-stars.interactive .star': '_onStarClick',
        'mouseenter .partner-review-stars.interactive .star': '_onStarHover',
        'mouseleave .partner-review-stars.interactive': '_onStarLeave',
        'click #btn-enviar-rating': '_onEnviarRating',
        'click #btn-eliminar-rating': '_onEliminarRating',
        'submit #comentario-form': '_onEnviarComentario',
        'click #btn-cargar-mas': '_onCargarMas',
        'click .btn-responder': '_onMostrarFormularioRespuesta',
        'click .btn-cancelar-respuesta': '_onOcultarFormularioRespuesta',
        'submit .form-respuesta-inline': '_onEnviarRespuesta',
        'click .btn-eliminar-comentario': '_onEliminarComentario',
        'click #btn-confirmar-eliminar': '_onConfirmarEliminar',
    },

    start: function () {
        this.config = window.PARTNER_REVIEWS_CONFIG || {};
        this.partnerId = this.config.partnerId;
        this.offset = 0;
        this.limit = 10;
        this.userRating = 0;
        this.commentToDelete = null;

        if (this.config.isLoggedIn) {
            this._cargarMiValoracion();
        }
        this._cargarComentarios();
        this._updateStarsDisplay(this.$('.partner-review-stars[data-readonly="1"]'), parseFloat(this.$('.display-4').text()) || 0);
        return this._super.apply(this, arguments);
    },

    _updateStarsDisplay: function ($container, rating) {
        if (!$container || !$container.length) return;
        $container.find('.star').each(function () {
            const val = parseInt($(this).data('value'));
            $(this).toggleClass('active', val <= rating);
        });
    },

    _onStarHover: function (ev) {
        const val = parseInt($(ev.currentTarget).data('value'));
        this._updateStarsDisplay($(ev.currentTarget).closest('.partner-review-stars'), val);
    },

    _onStarLeave: function (ev) {
        this._updateStarsDisplay($(ev.currentTarget), this.userRating);
    },

    _onStarClick: function (ev) {
        this.userRating = parseInt($(ev.currentTarget).data('value'));
        this._updateStarsDisplay($(ev.currentTarget).closest('.partner-review-stars'), this.userRating);
    },

    _cargarMiValoracion: function () {
        const self = this;
        $.ajax({
            url: '/partner-reviews/rating/mi-valoracion',
            data: {partner_id: self.partnerId},
            success: function (res) {
                if (res.success && res.rating) {
                    self.userRating = res.rating;
                    self._updateStarsDisplay(self.$('#rating-form'), self.userRating);
                    self.$('#btn-eliminar-rating').removeClass('d-none');
                }
            }
        });
    },

    _onEnviarRating: function () {
        const self = this;
        if (!this.config.isLoggedIn) {
            window.location.href = '/web/login?redirect=/resenas';
            return;
        }
        if (!this.userRating) {
            self.$('#rating-mensaje')
                .removeClass('d-none alert-success alert-danger')
                .addClass('alert-danger')
                .text('Selecciona una valoración.');
            return;
        }
        $.ajax({
            url: '/partner-reviews/rating/enviar',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({partner_id: self.partnerId, rating: self.userRating}),
            success: function (res) {
                if (res.success) {
                    self.$('#rating-mensaje')
                        .removeClass('d-none alert-danger')
                        .addClass('alert-success')
                        .text(res.mensaje);
                    self.$('#btn-eliminar-rating').removeClass('d-none');
                    self.$('.display-4').text(res.rating_avg.toFixed(1));
                } else {
                    self.$('#rating-mensaje')
                        .removeClass('d-none alert-success')
                        .addClass('alert-danger')
                        .text(res.error || 'Error');
                }
            },
            error: function () {
                self.$('#rating-mensaje')
                    .removeClass('d-none alert-success')
                    .addClass('alert-danger')
                    .text('Error de conexión.');
            }
        });
    },

    _onEliminarRating: function () {
        const self = this;
        $.ajax({
            url: '/partner-reviews/rating/eliminar',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({partner_id: self.partnerId}),
            success: function (res) {
                if (res.success) {
                    self.userRating = 0;
                    self._updateStarsDisplay(self.$('#rating-form'), 0);
                    self.$('#rating-mensaje')
                        .removeClass('d-none alert-danger')
                        .addClass('alert-success')
                        .text(res.mensaje);
                    self.$('#btn-eliminar-rating').addClass('d-none');
                    self.$('.display-4').text(res.rating_avg.toFixed(1));
                } else {
                    self.$('#rating-mensaje')
                        .removeClass('d-none alert-success')
                        .addClass('alert-danger')
                        .text(res.error || 'Error');
                }
            },
            error: function () {
                self.$('#rating-mensaje')
                    .removeClass('d-none alert-success')
                    .addClass('alert-danger')
                    .text('Error de conexión.');
            }
        });
    },

    _onEnviarComentario: function (ev) {
        ev.preventDefault();
        const self = this;
        const contenido = this.$('#comment-content').val().trim();
        if (!contenido) {
            self._mostrarMensajeComentario('Escribe un comentario.', 'danger');
            return;
        }
        $.ajax({
            url: '/partner-reviews/comment/enviar',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({partner_id: self.partnerId, contenido: contenido}),
            success: function (res) {
                if (res.success) {
                    self.$('#comment-content').val('');
                    const msg = res.mensaje || 'Comentario enviado.';
                    self._mostrarMensajeComentario(msg, 'success');
                    self.offset = 0;
                    self._cargarComentarios();
                } else {
                    self._mostrarMensajeComentario(res.error || 'Error', 'danger');
                }
            },
            error: function () {
                self._mostrarMensajeComentario('Error de conexión.', 'danger');
            }
        });
    },

    _mostrarMensajeComentario: function (mensaje, tipo) {
        this.$('#comment-mensaje')
            .removeClass('d-none alert-success alert-danger')
            .addClass('alert-' + tipo)
            .text(mensaje);
    },

    _cargarComentarios: function () {
        const self = this;
        $.ajax({
            url: '/partner-reviews/comment/listar',
            data: {partner_id: self.partnerId, offset: self.offset, limit: self.limit},
            success: function (res) {
                if (!res.success) {
                    self.$('#comentarios-lista').html('<p class="text-muted">' + escapeHtml(res.error || 'Error al cargar comentarios.') + '</p>');
                    self.$('#total-comentarios').text('0');
                    return;
                }
                const comentarios = res.comentarios || [];
                if (self.offset === 0) {
                    self.$('#comentarios-lista').empty();
                }
                if (comentarios.length === 0 && self.offset === 0) {
                    self.$('#comentarios-lista').html('<p class="text-muted">No hay comentarios aún. Sé el primero en comentar.</p>');
                }
                comentarios.forEach(function (c) {
                    const html = self._renderComentario(c);
                    self.$('#comentarios-lista').append(html);
                });
                self.$('#btn-cargar-mas').toggleClass('d-none', !res.tiene_mas);
                self.$('#total-comentarios').text(res.total || 0);
            },
            error: function () {
                self.$('#comentarios-lista').html('<p class="text-muted">Error de conexión.</p>');
            }
        });
    },

    _renderComentario: function (c) {
        const isLoggedIn = this.config.isLoggedIn;
        const esEmpleado = this.config.esEmpleadoPartner;
        const permitirComentarios = this.config.permitirComentarios;
        const currentUserId = this.config.userId;
        const isModerator = this.config.isModerator;
        const puedeEliminar = isLoggedIn && (c.autor_id === currentUserId || isModerator);

        let html = '<div class="card border-0 shadow-sm mb-3 comentario-item" id="comentario-' + c.id + '">';
        html += '<div class="card-body">';
        html += '<div class="d-flex">';
        html += '<img src="' + escapeHtml(c.autor_imagen_url || '/web/static/img/user_placeholder.jpg') + '" class="comentario-avatar me-3 bg-light" alt=""/>';
        html += '<div class="flex-grow-1">';
        html += '<div class="d-flex justify-content-between align-items-start">';
        html += '<h6 class="mb-1 fw-bold">' + escapeHtml(c.autor_nombre || 'Anónimo') + '</h6>';
        html += '<div class="d-flex align-items-center gap-2">';
        html += '<small class="text-muted">' + escapeHtml(c.fecha || '') + '</small>';
        if (puedeEliminar) {
            const titleDelete = (c.autor_id === currentUserId) ? 'Eliminar mi comentario' : 'Eliminar comentario (moderador)';
            html += '<button class="btn btn-link btn-sm p-0 text-danger btn-eliminar-comentario" data-id="' + c.id + '" title="' + titleDelete + '">';
            html += '<i class="fa fa-trash"></i>';
            html += '</button>';
        }
        html += '</div>';
        html += '</div>';
        html += '<p class="mb-2">' + escapeHtml(c.contenido || '') + '</p>';

        if (isLoggedIn && permitirComentarios) {
            html += '<button class="btn btn-sm btn-link p-0 text-decoration-none btn-responder" data-id="' + c.id + '" title="Responder">';
            html += '<i class="fa fa-reply"></i>';
            html += '</button>';
        }

        if (c.respuestas && c.respuestas.length) {
            html += '<div class="mt-3 ms-4 border-start border-2 border-primary ps-3">';
            c.respuestas.forEach(function (r) {
                html += '<div class="mb-2 respuesta-item" id="comentario-' + r.id + '">';
                html += '<div class="d-flex">';
                html += '<img src="' + escapeHtml(r.autor_imagen_url || '/web/static/img/user_placeholder.jpg') + '" class="comentario-avatar-sm me-2 bg-light" alt=""/>';
                html += '<div class="flex-grow-1">';
                html += '<div class="d-flex justify-content-between align-items-start">';
                html += '<small class="fw-bold">' + escapeHtml(r.autor_nombre || 'Anónimo') + '</small>';
                html += '<small class="text-muted">' + escapeHtml(r.fecha || '') + '</small>';
                html += '</div>';
                html += '<small>' + escapeHtml(r.contenido || '') + '</small>';
                html += '</div></div></div>';
            });
            html += '</div>';
        }

        if (isLoggedIn && permitirComentarios) {
            html += '<div id="respuesta-form-' + c.id + '" class="d-none respuesta-form-inline ms-4 border-start border-2 border-primary ps-3">';
            html += '<form class="form-respuesta-inline">';
            html += '<textarea class="form-control form-control-sm" rows="2" placeholder="Escribe tu respuesta..." required></textarea>';
            html += '<div class="mt-2">';
            html += '<button type="submit" class="btn btn-sm btn-primary">Responder</button>';
            html += '<button type="button" class="btn btn-sm btn-link btn-cancelar-respuesta">Cancelar</button>';
            html += '</div></form></div>';
        }

        html += '</div></div></div></div>';
        return html;
    },

    _onCargarMas: function () {
        this.offset += this.limit;
        this._cargarComentarios();
    },

    _onMostrarFormularioRespuesta: function (ev) {
        ev.preventDefault();
        const parentId = $(ev.currentTarget).data('id');
        this.$('#respuesta-form-' + parentId).removeClass('d-none');
    },

    _onOcultarFormularioRespuesta: function (ev) {
        ev.preventDefault();
        const $form = $(ev.currentTarget).closest('.respuesta-form-inline');
        $form.addClass('d-none');
        $form.find('textarea').val('');
    },

    _onEnviarRespuesta: function (ev) {
        ev.preventDefault();
        const self = this;
        const $form = $(ev.currentTarget);
        const parentId = $form.closest('.respuesta-form-inline').attr('id').replace('respuesta-form-', '');
        const contenido = $form.find('textarea').val().trim();
        if (!contenido) return;

        $.ajax({
            url: '/partner-reviews/comment/enviar',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({partner_id: self.partnerId, contenido: contenido, parent_id: parseInt(parentId)}),
            success: function (res) {
                if (res.success) {
                    self.offset = 0;
                    self._cargarComentarios();
                } else {
                    alert(res.error || 'Error al enviar respuesta');
                }
            },
            error: function () {
                alert('Error de conexión.');
            }
        });
    },

    _onEliminarComentario: function (ev) {
        ev.preventDefault();
        this.commentToDelete = $(ev.currentTarget).data('id');
        const modalEl = document.getElementById('modal-eliminar-comentario');
        if (modalEl && window.bootstrap) {
            const modal = new window.bootstrap.Modal(modalEl);
            modal.show();
        } else if (modalEl) {
            // Fallback si bootstrap no está disponible
            $(modalEl).modal('show');
        }
    },

    _onConfirmarEliminar: function () {
        const self = this;
        const commentId = this.commentToDelete;
        if (!commentId) return;

        // Cerrar modal
        const modalEl = document.getElementById('modal-eliminar-comentario');
        if (modalEl && window.bootstrap) {
            const modal = window.bootstrap.Modal.getInstance(modalEl);
            if (modal) modal.hide();
        } else if (modalEl) {
            $(modalEl).modal('hide');
        }

        $.ajax({
            url: '/partner-reviews/comment/eliminar',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({comment_id: commentId}),
            success: function (res) {
                self.commentToDelete = null;
                if (res.success) {
                    self.offset = 0;
                    self._cargarComentarios();
                } else {
                    alert(res.error || 'Error al eliminar comentario');
                }
            },
            error: function () {
                self.commentToDelete = null;
                alert('Error de conexión.');
            }
        });
    },
});
// Cache-bust: 20260508051533
