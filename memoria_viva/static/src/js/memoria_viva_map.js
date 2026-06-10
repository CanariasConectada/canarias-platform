/* ========================================
   MEMORIA VIVA - MAPAS (Google + OpenStreetMap)
   ======================================== */

odoo.define('memoria_viva.map', function (require) {
    'use strict';

    try {
        var publicWidget = require('web.public.widget');
    } catch (e) {
        console.warn('[MemoriaViva] web.public.widget no disponible, mapa no cargado');
        return;
    }

    // ========================================
    // MAPA PRINCIPAL
    // ========================================
    publicWidget.registry.MemoriaVivaMap = publicWidget.Widget.extend({
        selector: '#memoria-viva-map',
        
        start: function () {
            this._super.apply(this, arguments);
            this._loadMap();
        },

        _loadMap: function () {
            var self = this;
            var mapContainer = this.$el[0];
            
            // Leer datos
            var dataElement = document.getElementById('memoria-viva-lugares-data');
            this.lugaresData = [];
            
            if (dataElement) {
                try {
                    this.lugaresData = JSON.parse(dataElement.textContent.trim());
                } catch (e) {
                    console.error('[Memoria Viva] Error parsing lugares data:', e);
                }
            }
            
            if (!this.lugaresData || this.lugaresData.length === 0) {
                this.$el.html('<div class="alert alert-info text-center m-4">No hay lugares con ubicación para mostrar.</div>');
                return;
            }

            // Intentar Google Maps primero
            if (typeof google !== 'undefined' && google.maps) {
                this._initGoogleMap();
            } else {
                // Cargar OpenStreetMap
                this._loadLeaflet();
            }
        },

        // ========================================
        // GOOGLE MAPS
        // ========================================
        _initGoogleMap: function () {
            var self = this;
            var mapContainer = this.$el[0];
            
            var bounds = new google.maps.LatLngBounds();
            this.lugaresData.forEach(function (lugar) {
                bounds.extend(new google.maps.LatLng(lugar.lat, lugar.lng));
            });

            var map = new google.maps.Map(mapContainer, {
                zoom: 13,
                center: bounds.getCenter(),
                mapTypeId: google.maps.MapTypeId.ROADMAP,
            });

            this.lugaresData.forEach(function (lugar) {
                var marker = new google.maps.Marker({
                    position: { lat: lugar.lat, lng: lugar.lng },
                    map: map,
                    title: lugar.name,
                });

                var infowindow = new google.maps.InfoWindow({
                    content: '<div style="max-width:200px;"><h6>' + lugar.name + '</h6><a href="/memoria-viva/' + lugar.slug + '">Ver →</a></div>',
                });

                marker.addListener('click', function () {
                    infowindow.open(map, marker);
                });
            });

            map.fitBounds(bounds);
            console.log('[Memoria Viva] Google Maps inicializado');
        },

        // ========================================
        // OPENSTREETMAP (Leaflet)
        // ========================================
        _loadLeaflet: function () {
            var self = this;
            
            // Cargar CSS
            if (!document.getElementById('leaflet-css')) {
                var link = document.createElement('link');
                link.id = 'leaflet-css';
                link.rel = 'stylesheet';
                link.href = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css';
                document.head.appendChild(link);
            }

            // Cargar JS
            if (typeof L === 'undefined') {
                var script = document.createElement('script');
                script.src = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js';
                script.onload = function () {
                    self._initLeafletMap();
                };
                script.onerror = function () {
                    self.$el.html('<div class="alert alert-warning text-center m-4">Error al cargar el mapa.</div>');
                };
                document.head.appendChild(script);
            } else {
                this._initLeafletMap();
            }
        },

        _initLeafletMap: function () {
            var self = this;
            var container = this.$el[0];
            
            // Calcular centro
            var lats = this.lugaresData.map(function (l) { return l.lat; });
            var lngs = this.lugaresData.map(function (l) { return l.lng; });
            var centerLat = (Math.min.apply(null, lats) + Math.max.apply(null, lats)) / 2;
            var centerLng = (Math.min.apply(null, lngs) + Math.max.apply(null, lngs)) / 2;

            var map = L.map(container).setView([centerLat, centerLng], 13);

            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                attribution: '&copy; OpenStreetMap contributors',
                maxZoom: 19,
            }).addTo(map);

            var markers = [];
            this.lugaresData.forEach(function (lugar) {
                var marker = L.marker([lugar.lat, lugar.lng])
                    .addTo(map)
                    .bindPopup('<strong>' + lugar.name + '</strong><br><a href="/memoria-viva/' + lugar.slug + '">Ver historia →</a>');
                markers.push(marker);
            });

            if (markers.length > 0) {
                var group = new L.featureGroup(markers);
                map.fitBounds(group.getBounds().pad(0.1));
            }
            
            console.log('[Memoria Viva] OpenStreetMap inicializado con', this.lugaresData.length, 'marcadores');
        },
    });

    // ========================================
    // FORMULARIO
    // ========================================
    publicWidget.registry.MemoriaVivaForm = publicWidget.Widget.extend({
        selector: '#form-memoria-viva',
        
        events: {
            'submit': '_onSubmit',
        },

        _onSubmit: function (ev) {
            ev.preventDefault();
            var self = this;
            var $form = this.$el;
            var $btn = $form.find('#btn-enviar');
            var $success = $('#mensaje-confirmacion');
            var $error = $('#mensaje-error');

            // Ocultar mensajes previos
            $success.hide();
            $error.hide();

            // Validar campos requeridos
            var name = $form.find('[name="name"]').val();
            var email = $form.find('[name="publicador_email"]').val();
            var imageFile = $form.find('[name="image"]')[0].files[0];

            if (!name || !email || !imageFile) {
                $('#texto-error').text('Por favor complete todos los campos requeridos.');
                $error.show();
                return;
            }

            $btn.prop('disabled', true).html('<i class="fa fa-spinner fa-spin"></i> Enviando...');

            // Leer imagen
            var reader = new FileReader();
            reader.onload = function (e) {
                var data = {
                    name: name,
                    description: $form.find('[name="description"]').val(),
                    image_main: e.target.result,
                    direccion: $form.find('[name="direccion"]').val(),
                    publicador_nombre: $form.find('[name="publicador_nombre"]').val(),
                    publicador_email: email,
                    publicador_telefono: $form.find('[name="publicador_telefono"]').val(),
                };

                // Enviar
                $.ajax({
                    url: '/memoria_viva/api/submit',
                    type: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify(data),
                    success: function (response) {
                        if (response.success) {
                            $form[0].reset();
                            $success.show();
                            $('html, body').animate({
                                scrollTop: $success.offset().top - 100
                            }, 500);
                        } else {
                            $('#texto-error').text(response.error || 'Error al enviar.');
                            $error.show();
                        }
                    },
                    error: function (xhr) {
                        $('#texto-error').text('Error de conexión. Intente nuevamente.');
                        $error.show();
                    },
                    complete: function () {
                        $btn.prop('disabled', false).html('<i class="fa fa-paper-plane"></i> Enviar historia');
                    },
                });
            };

            reader.onerror = function () {
                $('#texto-error').text('Error al leer la imagen.');
                $error.show();
                $btn.prop('disabled', false).html('<i class="fa fa-paper-plane"></i> Enviar historia');
            };

            reader.readAsDataURL(imageFile);
        },
    });

    return {
        MemoriaVivaMap: publicWidget.registry.MemoriaVivaMap,
        MemoriaVivaForm: publicWidget.registry.MemoriaVivaForm,
    };
});
