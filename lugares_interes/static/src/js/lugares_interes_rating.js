/* Lugares de Interés - Sistema de Valoración con Estrellas */
(function() {
    'use strict';
    
    document.addEventListener('DOMContentLoaded', function() {
        // Inicializar sistema de ratings si existe el contenedor
        if (document.getElementById('rating-input')) {
            initRatingSystem();
        }
    });
    
    /**
     * Inicializa el sistema de valoración
     */
    function initRatingSystem() {
        var lugarIdInput = document.getElementById('lugar_id');
        if (!lugarIdInput) {
            console.error('Rating: No se encontró lugar_id');
            return;
        }
        
        var lugarId = lugarIdInput.value;
        var starButtons = document.querySelectorAll('.rating-star-btn');
        var ratingValueInput = document.getElementById('user-rating-value');
        var btnEnviar = document.getElementById('btn-enviar-rating');
        var btnEliminar = document.getElementById('btn-eliminar-rating');
        var mensajeDiv = document.getElementById('rating-mensaje');
        var currentRating = 0;
        
        // Cargar valoración existente del usuario
        cargarMiValoracion(lugarId);
        
        // Event listeners para las estrellas
        starButtons.forEach(function(btn) {
            var rating = parseInt(btn.dataset.rating);
            var icon = btn.querySelector('i');
            
            // Hover: iluminar estrellas hasta esta
            btn.addEventListener('mouseenter', function() {
                highlightStars(rating);
            });
            
            // Mouse leave: restaurar a la selección actual
            btn.addEventListener('mouseleave', function() {
                highlightStars(currentRating);
            });
            
            // Click: seleccionar rating
            btn.addEventListener('click', function() {
                currentRating = rating;
                ratingValueInput.value = rating;
                highlightStars(rating);
                btnEnviar.classList.remove('d-none');
                mensajeDiv.classList.add('d-none');
            });
        });
        
        // Botón enviar
        if (btnEnviar) {
            btnEnviar.addEventListener('click', function() {
                enviarValoracion(lugarId, currentRating);
            });
        }
        
        // Botón eliminar
        if (btnEliminar) {
            btnEliminar.addEventListener('click', function() {
                eliminarValoracion(lugarId);
            });
        }
        
        /**
         * Ilumina las estrellas hasta el rating especificado
         */
        function highlightStars(rating) {
            starButtons.forEach(function(btn) {
                var btnRating = parseInt(btn.dataset.rating);
                var icon = btn.querySelector('i');
                if (btnRating <= rating) {
                    icon.classList.remove('fa-star-o');
                    icon.classList.add('fa-star');
                } else {
                    icon.classList.remove('fa-star');
                    icon.classList.add('fa-star-o');
                }
            });
        }
        
        /**
         * Carga la valoración existente del usuario
         */
        function cargarMiValoracion(lugarId) {
            fetch('/lugares-de-interes/rating/mi-valoracion?lugar_id=' + lugarId, {
                method: 'GET',
                headers: { 'Accept': 'application/json' },
                credentials: 'same-origin'
            })
            .then(function(r) { return r.json(); })
            .then(function(response) {
                var data = response.result || response;
                if (data.success && data.rating > 0) {
                    currentRating = data.rating;
                    ratingValueInput.value = data.rating;
                    highlightStars(data.rating);
                    btnEliminar.classList.remove('d-none');
                }
            })
            .catch(function(err) {
                console.error('Error cargando valoración:', err);
            });
        }
        
        /**
         * Envía la valoración al servidor
         */
        function enviarValoracion(lugarId, rating) {
            btnEnviar.disabled = true;
            btnEnviar.innerHTML = '<i class="fa fa-spinner fa-spin me-1"/>Enviando...';
            
            fetch('/lugares-de-interes/rating/enviar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    lugar_id: parseInt(lugarId),
                    rating: rating
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(response) {
                var data = response.result || response;
                
                if (data.success) {
                    // Mostrar mensaje de éxito
                    mensajeDiv.textContent = data.mensaje;
                    mensajeDiv.classList.remove('d-none');
                    btnEliminar.classList.remove('d-none');
                    
                    // Actualizar promedio visual
                    actualizarPromedioDisplay(data.rating_avg, data.rating_count);
                    
                    // Resetear botón
                    btnEnviar.classList.add('d-none');
                } else {
                    alert('Error: ' + (data.error || 'No se pudo enviar la valoración'));
                }
            })
            .catch(function(err) {
                console.error('Error:', err);
                alert('Error de conexión. Inténtalo de nuevo.');
            })
            .finally(function() {
                btnEnviar.disabled = false;
                btnEnviar.innerHTML = '<i class="fa fa-paper-plane me-1"/>Enviar valoración';
            });
        }
        
        /**
         * Elimina la valoración del usuario
         */
        function eliminarValoracion(lugarId) {
            if (!confirm('¿Estás seguro de que quieres eliminar tu valoración?')) {
                return;
            }
            
            btnEliminar.disabled = true;
            
            fetch('/lugares-de-interes/rating/eliminar', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    lugar_id: parseInt(lugarId)
                })
            })
            .then(function(r) { return r.json(); })
            .then(function(response) {
                var data = response.result || response;
                
                if (data.success) {
                    // Resetear estrellas
                    currentRating = 0;
                    ratingValueInput.value = 0;
                    highlightStars(0);
                    
                    // Ocultar botones
                    btnEnviar.classList.add('d-none');
                    btnEliminar.classList.add('d-none');
                    mensajeDiv.classList.add('d-none');
                    
                    // Actualizar promedio visual
                    actualizarPromedioDisplay(data.rating_avg, data.rating_count);
                    
                    alert(data.mensaje);
                } else {
                    alert('Error: ' + (data.error || 'No se pudo eliminar la valoración'));
                }
            })
            .catch(function(err) {
                console.error('Error:', err);
                alert('Error de conexión. Inténtalo de nuevo.');
            })
            .finally(function() {
                btnEliminar.disabled = false;
            });
        }
        
        /**
         * Actualiza el display del promedio
         */
        function actualizarPromedioDisplay(avg, count) {
            // Actualizar número
            var avgSpan = document.querySelector('#rating-display').previousElementSibling.querySelector('.display-4');
            if (avgSpan) {
                avgSpan.textContent = avg.toFixed(1);
            }
            
            // Actualizar conteo
            var countSpan = document.querySelector('#rating-display').nextElementSibling.querySelector('span');
            if (countSpan) {
                countSpan.textContent = count;
            }
            
            // Actualizar estrellas del promedio
            var displayContainer = document.getElementById('rating-display');
            if (displayContainer) {
                var fullStars = Math.floor(avg);
                var hasHalf = (avg - fullStars) >= 0.5;
                var html = '';
                
                for (var i = 0; i < 5; i++) {
                    if (i < fullStars) {
                        html += '<i class="fa fa-star text-warning fs-5"/> ';
                    } else if (i === fullStars && hasHalf) {
                        html += '<i class="fa fa-star-half-o text-warning fs-5"/> ';
                    } else {
                        html += '<i class="fa fa-star-o text-muted fs-5"/> ';
                    }
                }
                displayContainer.innerHTML = html;
            }
        }
    }
})();
