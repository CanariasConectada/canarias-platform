// Búsqueda asíncrona para la tienda (/shop)
// Similar a la implementación del directorio

(function() {
    'use strict';
    
    function initShopAsyncSearch() {
        // Verificar si estamos en la tienda
        if (!window.location.pathname.startsWith('/shop')) {
            return;
        }
        
        // Esperar a que jQuery esté disponible
        if (typeof jQuery === 'undefined') {
            setTimeout(initShopAsyncSearch, 200);
            return;
        }
        
        var $ = jQuery;
        var isLoading = false;
        var searchTimeout = null;
        
        // Función para obtener parámetros actuales de URL
        function getCurrentParams() {
            var urlParams = new URLSearchParams(window.location.search);
            return {
                search: urlParams.get('search') || '',
                category: urlParams.get('category') || '',
                page: urlParams.get('page') || '1',
            };
        }
        
        // Función para construir query string
        function buildQueryString(params) {
            var parts = [];
            if (params.search) parts.push('search=' + encodeURIComponent(params.search));
            if (params.category) parts.push('category=' + encodeURIComponent(params.category));
            if (params.page && params.page !== '1') parts.push('page=' + encodeURIComponent(params.page));
            return parts.length > 0 ? '?' + parts.join('&') : '';
        }
        
        // Función para cargar datos asíncronos
        function loadAsyncData(search, category) {
            if (isLoading) return;
            isLoading = true;
            
            // Mostrar loading
            $('#o_wsale_products_grid').css('opacity', '0.5');
            
            $.ajax({
                url: '/shop/search_async',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({
                    jsonrpc: '2.0',
                    method: 'call',
                    params: {
                        search: search,
                        category: category,
                    },
                    id: Math.floor(Math.random() * 1000000)
                }),
                success: function(result) {
                    if (result.result && result.result.success) {
                        // Actualizar grid de productos
                        if (result.result.html) {
                            var $gridSection = $('#o_wsale_products_grid');
                            if ($gridSection.length) {
                                // Reemplazar el contenido interno del section
                                $gridSection.html(result.result.html);
                                
                                // Asegurar que las clases CSS del grid estén correctas
                                $gridSection.addClass('o_wsale_products_grid_table grid');
                                if (!$gridSection.hasClass('o_wsale_products_grid_table_md')) {
                                    $gridSection.addClass('o_wsale_products_grid_table_md');
                                }
                            } else {
                                // Fallback: buscar el wrapper
                                var $wrapper = $('.o_wsale_products_grid_table_wrapper');
                                if ($wrapper.length) {
                                    $wrapper.html('<section id="o_wsale_products_grid" class="o_wsale_products_grid_table grid o_wsale_products_grid_table_md">' + result.result.html + '</section>');
                                }
                            }
                        }
                        
                        // Actualizar contador de resultados si existe
                        if (result.result.products_count !== undefined) {
                            var $counter = $('.o_wsale_products_count, .products_header .text-muted');
                            if ($counter.length) {
                                $counter.text(result.result.products_count + ' productos');
                            }
                        }
                        
                        // Actualizar URL sin recargar
                        if (window.history && window.history.pushState) {
                            var params = getCurrentParams();
                            params.search = search;
                            params.category = category;
                            var url = '/shop' + buildQueryString(params);
                            window.history.pushState({ shopAsync: true }, document.title, url);
                        }
                    } else {
                        // Si falla, hacer redirección normal
                        var params = getCurrentParams();
                        params.search = search;
                        window.location.href = '/shop' + buildQueryString(params);
                    }
                },
                error: function() {
                    // En error, redirigir normalmente
                    var params = getCurrentParams();
                    params.search = search;
                    window.location.href = '/shop' + buildQueryString(params);
                },
                complete: function() {
                    isLoading = false;
                    $('#o_wsale_products_grid').css('opacity', '1');
                }
            });
        }
        
        // Función principal para inicializar eventos
        function initEvents() {
            // Prevenir submit del formulario de búsqueda
            $(document).off('submit.shopAsync').on('submit.shopAsync', 'form[action="/shop"]', function(e) {
                e.preventDefault();
                var $input = $(this).find('input[name="search"]');
                var search = $input.val() || '';
                var params = getCurrentParams();
                loadAsyncData(search, params.category);
                return false;
            });
            
            // Input de búsqueda con debounce (500ms después de dejar de escribir)
            $(document).off('input.shopAsync').on('input.shopAsync', 'input[name="search"]', function(e) {
                var val = $(this).val();
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(function() {
                    var params = getCurrentParams();
                    loadAsyncData(val, params.category);
                }, 500);
            });
            
            // Capturar Enter en el input de búsqueda
            $(document).off('keydown.shopAsync').on('keydown.shopAsync', 'input[name="search"]', function(e) {
                if (e.which === 13) {
                    e.preventDefault();
                    clearTimeout(searchTimeout);
                    var val = $(this).val();
                    var params = getCurrentParams();
                    loadAsyncData(val, params.category);
                    return false;
                }
            });
        }
        
        // Inicializar eventos
        initEvents();
    }
    
    // Iniciar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShopAsyncSearch);
    } else {
        initShopAsyncSearch();
    }
    
    // También intentar después de un delay
    setTimeout(initShopAsyncSearch, 1000);
})();
