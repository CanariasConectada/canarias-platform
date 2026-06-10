/* Lugares de Interés - Sistema de Comentarios */
(function() {
    'use strict';
    
    // Variables globales
    var offset = 0;
    var cargando = false;
    
    document.addEventListener('DOMContentLoaded', function() {
        // Inicializar comentarios si existe la sección
        if (document.getElementById('comentarios-lista')) {
            cargarComentarios(0);
            
            // Inicializar formulario si existe
            var form = document.getElementById('comentarioForm');
            if (form) {
                initComentarioForm();
            }
        }
    });
    
    /**
     * Carga los comentarios vía AJAX
     */
    function cargarComentarios(nuevoOffset) {
        if (cargando) return;
        
        var lista = document.getElementById('comentarios-lista');
        var lugarIdInput = document.getElementById('lugar_id') || document.querySelector('input[name="lugar_id"]');
        
        if (!lugarIdInput || !lista) return;
        
        var lugarId = lugarIdInput.value;
        offset = nuevoOffset !== undefined ? nuevoOffset : offset;
        cargando = true;
        
        // Mostrar indicador de carga
        if (offset === 0) {
            lista.innerHTML = '<div class="text-center py-4"><i class="fa fa-spinner fa-spin fa-2x text-primary"></i></div>';
        }
        
        fetch('/lugares-de-interes/comentario/listar?lugar_id=' + lugarId + '&offset=' + offset + '&limit=10', {
            method: 'GET',
            headers: {
                'Accept': 'application/json'
            },
            credentials: 'same-origin'
        })
        .then(function(response) { 
            if (!response.ok) {
                throw new Error('HTTP ' + response.status);
            }
            return response.json(); 
        })
        .then(function(response) {
            var data = response.result || response;
            cargando = false;
            
            if (data.success) {
                // Limpiar indicador de carga
                if (offset === 0) {
                    lista.innerHTML = '';
                }
                
                // Renderizar comentarios
                data.comentarios.forEach(function(comentario) {
                    lista.appendChild(renderizarComentario(comentario));
                });
                
                // Actualizar contador total
                var totalEl = document.getElementById('total-comentarios');
                if (totalEl) {
                    totalEl.textContent = data.total || 0;
                }
                
                // Mostrar/ocultar botón "ver más"
                var verMasBtn = document.getElementById('verMasComentarios');
                if (verMasBtn) {
                    if (data.tiene_mas) {
                        verMasBtn.classList.remove('d-none');
                        verMasBtn.onclick = function() {
                            cargarComentarios(offset + 10);
                        };
                    } else {
                        verMasBtn.classList.add('d-none');
                    }
                }
                
                // Si no hay comentarios
                if (data.total === 0) {
                    lista.innerHTML = '<p class="text-muted text-center py-4">No hay comentarios aún. ¡Sé el primero en comentar!</p>';
                }
            }
        })
        .catch(function(err) {
            console.error('Error cargando comentarios:', err);
            cargando = false;
        });
    }
    
    /**
     * Renderiza un comentario en HTML
     */
    function renderizarComentario(comentario) {
        var div = document.createElement('div');
        div.className = 'card border-0 shadow-sm mb-3';
        div.id = 'comentario-' + comentario.id;
        
        var html = '<div class="card-body">';
        html += '<div class="d-flex">';
        
        // Avatar
        var avatarUrl = comentario.autor_imagen_url || '/web/static/img/user_placeholder.jpg';
        html += '<img src="' + escapeHtml(avatarUrl) + '" class="rounded-circle me-3 bg-light" style="width: 50px; height: 50px; object-fit: cover;"/>';
        
        html += '<div class="flex-grow-1">';
        html += '<div class="d-flex justify-content-between align-items-start">';
        html += '<h6 class="mb-1 fw-bold">' + escapeHtml(comentario.autor_nombre) + '</h6>';
        html += '<small class="text-muted">' + escapeHtml(comentario.fecha) + '</small>';
        html += '</div>';
        html += '<p class="mb-2">' + escapeHtml(comentario.contenido).replace(/\n/g, '<br/>') + '</p>';
        
        // Botón responder (solo usuarios logueados)
        if (!document.querySelector('.alert-info a[href="/web/login"]')) {
            html += '<button class="btn btn-sm btn-link p-0 text-decoration-none" onclick="mostrarFormularioRespuesta(' + comentario.id + ')">';
            html += '<i class="fa fa-reply me-1"/>Responder';
            html += '</button>';
        }
        
        // Contenedor para respuestas
        if (comentario.respuestas && comentario.respuestas.length > 0) {
            html += '<div class="mt-3 ms-4 border-start border-2 border-primary ps-3">';
            comentario.respuestas.forEach(function(resp) {
                html += '<div class="mb-2" id="comentario-' + resp.id + '">';
                html += '<div class="d-flex">';
                var respAvatar = resp.autor_imagen_url || '/web/static/img/user_placeholder.jpg';
                html += '<img src="' + escapeHtml(respAvatar) + '" class="rounded-circle me-2" style="width: 30px; height: 30px; object-fit: cover;"/>';
                html += '<div class="flex-grow-1">';
                html += '<div class="d-flex justify-content-between align-items-start">';
                html += '<small class="fw-bold">' + escapeHtml(resp.autor_nombre) + '</small>';
                html += '<small class="text-muted">' + escapeHtml(resp.fecha) + '</small>';
                html += '</div>';
                html += '<small>' + escapeHtml(resp.contenido).replace(/\n/g, '<br/>') + '</small>';
                html += '</div></div></div>';
            });
            html += '</div>';
        }
        
        // Formulario de respuesta (inicialmente oculto)
        html += '<div id="respuesta-form-' + comentario.id + '" class="d-none mt-3 ms-4">';
        html += '<form onsubmit="enviarRespuesta(event, ' + comentario.id + ')">';
        html += '<textarea class="form-control form-control-sm" rows="2" placeholder="Escribe tu respuesta..." required></textarea>';
        html += '<div class="mt-2">';
        html += '<button type="submit" class="btn btn-sm btn-primary">Responder</button>';
        html += '<button type="button" class="btn btn-sm btn-link" onclick="ocultarFormularioRespuesta(' + comentario.id + ')">Cancelar</button>';
        html += '</div></form></div>';
        
        html += '</div></div></div>';
        div.innerHTML = html;
        
        return div;
    }
    
    /**
     * Inicializa el formulario de comentarios
     */
    function initComentarioForm() {
        var form = document.getElementById('comentarioForm');
        if (!form) return;
        
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            
            var submitBtn = form.querySelector('button[type="submit"]');
            var successDiv = document.getElementById('comentarioSuccess');
            var errorDiv = document.getElementById('comentarioError');
            
            successDiv.classList.add('d-none');
            errorDiv.classList.add('d-none');
            
            var formData = new FormData(form);
            var contenido = formData.get('contenido') || '';
            var lugarId = formData.get('lugar_id');
            
            if (!contenido.trim()) {
                errorDiv.textContent = 'El comentario no puede estar vacío.';
                errorDiv.classList.remove('d-none');
                return;
            }
            
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin me-2"/>Enviando...';
            
            fetch('/lugares-de-interes/comentario/enviar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    lugar_id: parseInt(lugarId),
                    contenido: contenido.trim()
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(response) {
                var data = response.result || response;
                
                if (data.success) {
                    form.reset();
                    if (data.estado === 'aprobado') {
                        successDiv.innerHTML = '<i class="fa fa-check-circle me-2"/>¡Comentario publicado correctamente!';
                    } else {
                        successDiv.innerHTML = '<i class="fa fa-clock me-2"/>Tu comentario está pendiente de aprobación. Será visible tras revisión.';
                    }
                    successDiv.classList.remove('d-none');
                    successDiv.scrollIntoView({ behavior: 'smooth' });
                    
                    // Si fue aprobado, recargar comentarios
                    if (data.estado === 'aprobado') {
                        cargarComentarios(0);
                    }
                } else {
                    errorDiv.textContent = data.error || 'Error al enviar el comentario.';
                    errorDiv.classList.remove('d-none');
                }
            })
            .catch(function(err) {
                errorDiv.textContent = 'Error de conexión. Inténtalo de nuevo.';
                errorDiv.classList.remove('d-none');
            })
            .finally(function() {
                submitBtn.disabled = false;
                submitBtn.innerHTML = '<i class="fa fa-paper-plane me-2"/>Enviar';
            });
        });
    }
    
    // Exponer funciones globales
    window.mostrarFormularioRespuesta = function(comentarioId) {
        var form = document.getElementById('respuesta-form-' + comentarioId);
        if (form) {
            form.classList.remove('d-none');
            form.querySelector('textarea').focus();
        }
    };
    
    window.ocultarFormularioRespuesta = function(comentarioId) {
        var form = document.getElementById('respuesta-form-' + comentarioId);
        if (form) {
            form.classList.add('d-none');
        }
    };
    
    window.enviarRespuesta = function(e, parentId) {
        e.preventDefault();
        var form = e.target;
        var textarea = form.querySelector('textarea');
        var contenido = textarea.value.trim();
        var lugarId = document.querySelector('input[name="lugar_id"]').value;
        
        if (!contenido) return;
        
        var submitBtn = form.querySelector('button[type="submit"]');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<i class="fa fa-spinner fa-spin me-1"/>Enviando...';
        
        fetch('/lugares-de-interes/comentario/enviar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                lugar_id: parseInt(lugarId),
                contenido: contenido,
                parent_id: parentId
            })
        })
        .then(function(r) { return r.json(); })
        .then(function(response) {
            var data = response.result || response;
            
            if (data.success) {
                form.reset();
                ocultarFormularioRespuesta(parentId);
                
                if (data.estado === 'aprobado') {
                    cargarComentarios(0);
                } else {
                    // Mostrar mensaje temporal
                    var msg = document.createElement('div');
                    msg.className = 'alert alert-info mt-2';
                    msg.innerHTML = '<i class="fa fa-clock me-2"/>Tu respuesta está pendiente de aprobación.';
                    form.parentElement.appendChild(msg);
                    setTimeout(function() { msg.remove(); }, 3000);
                }
            }
        })
        .finally(function() {
            submitBtn.disabled = false;
            submitBtn.innerHTML = 'Responder';
        });
    };
    
    /**
     * Helper para escapar HTML
     */
    function escapeHtml(text) {
        if (typeof text !== 'string') return '';
        var div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
})();
