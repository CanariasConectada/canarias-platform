// Select2 para filtros de la tienda (/shop)
// Inicializa selects con búsqueda igual que en el directorio

(function() {
    'use strict';
    
    function initShopSelect2() {
        // Verificar si estamos en la tienda
        if (!window.location.pathname.startsWith('/shop')) {
            return;
        }
        
        // Esperar a que jQuery esté disponible
        if (typeof jQuery === 'undefined') {
            setTimeout(initShopSelect2, 200);
            return;
        }
        
        var $ = jQuery;
        
        // Cargar Select2 si no está disponible
        if (typeof $.fn.select2 === 'undefined') {
            loadSelect2($).then(function() {
                initializeSelects($);
            }).catch(function() {
                console.log('[ShopSelect2] No se pudo cargar Select2');
            });
        } else {
            initializeSelects($);
        }
    }
    
    function loadSelect2($) {
        return new Promise(function(resolve, reject) {
            // Cargar CSS si no está cargado
            if (!$('link[href*="select2.min.css"]').length) {
                $('<link>')
                    .attr('rel', 'stylesheet')
                    .attr('href', 'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css')
                    .appendTo('head');
                
                $('<link>')
                    .attr('rel', 'stylesheet')
                    .attr('href', 'https://cdn.jsdelivr.net/npm/select2-bootstrap-5-theme@1.3.0/dist/select2-bootstrap-5-theme.min.css')
                    .appendTo('head');
            }
            
            // Cargar JS
            $.getScript('https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js')
                .done(function() {
                    resolve();
                })
                .fail(function() {
                    reject();
                });
        });
    }
    
    function initializeSelects($) {
        // Select de Categorías
        var $catSelect = $('#category-select-shop');
        if ($catSelect.length && !$catSelect.hasClass('select2-hidden-accessible')) {
            $catSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Buscar categoría...',
                allowClear: false,
                language: {
                    noResults: function() {
                        return "No se encontró la categoría";
                    },
                    searching: function() {
                        return "Buscando...";
                    }
                }
            });
            
            // Manejar cambio
            $catSelect.on('change', function() {
                var url = $(this).val();
                if (url && url !== window.location.href) {
                    window.location.href = url;
                }
            });
        }
        
        // Select de Subcategorías
        var $subCatSelect = $('#subcategory-select-shop');
        if ($subCatSelect.length && !$subCatSelect.hasClass('select2-hidden-accessible')) {
            $subCatSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Buscar subcategoría...',
                allowClear: false,
                language: {
                    noResults: function() {
                        return "No se encontró la subcategoría";
                    },
                    searching: function() {
                        return "Buscando...";
                    }
                }
            });
            
            $subCatSelect.on('change', function() {
                var url = $(this).val();
                if (url && url !== window.location.href) {
                    window.location.href = url;
                }
            });
        }
        
        // Select de Zonas Comerciales
        var $zoneSelect = $('#zone-select-shop');
        if ($zoneSelect.length && !$zoneSelect.hasClass('select2-hidden-accessible')) {
            $zoneSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Buscar zona...',
                allowClear: false,
                language: {
                    noResults: function() {
                        return "No se encontró la zona";
                    },
                    searching: function() {
                        return "Buscando...";
                    }
                }
            });
            
            $zoneSelect.on('change', function() {
                var url = $(this).val();
                if (url && url !== window.location.href) {
                    window.location.href = url;
                }
            });
        }
        
        // Focus en el campo de búsqueda al abrir el select
        $(document).on('select2:open', function() {
            setTimeout(function() {
                var searchField = document.querySelector('.select2-container--open .select2-search__field');
                if (searchField) {
                    searchField.focus();
                }
            }, 100);
        });
    }
    
    // Iniciar cuando el DOM esté listo
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShopSelect2);
    } else {
        initShopSelect2();
    }
    
    // También intentar después de un delay por si hay carga AJAX
    setTimeout(initShopSelect2, 1000);
    setTimeout(initShopSelect2, 2000);
})();
