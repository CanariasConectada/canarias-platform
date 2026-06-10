// Select2 para filtros de la tienda (/shop) - Versión combobox con búsqueda

(function() {
    'use strict';
    
    function initShopSelect2() {
        if (!window.location.pathname.startsWith('/shop')) {
            return;
        }
        
        if (typeof jQuery === 'undefined') {
            setTimeout(initShopSelect2, 200);
            return;
        }
        
        var $ = jQuery;
        
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
        // Select de Categorías - COMBOBOX CON BÚSQUEDA
        var $catSelect = $('#category-select-shop');
        if ($catSelect.length && !$catSelect.hasClass('select2-hidden-accessible')) {
            // Usar el contenedor del acordeón como padre para que el dropdown pueda salir
            var $parent = $catSelect.closest('.products_categories, #products_grid_before, body');
            
            $catSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Buscar categoría...',
                allowClear: false,
                dropdownParent: $parent.length ? $parent.first() : $('body'),
                language: {
                    noResults: function() {
                        return "No se encontró la categoría";
                    },
                    searching: function() {
                        return "Buscando...";
                    }
                }
            });
            
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
            var $subParent = $subCatSelect.closest('.products_categories, #products_grid_before, body');
            
            $subCatSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Buscar subcategoría...',
                allowClear: false,
                dropdownParent: $subParent.length ? $subParent.first() : $('body'),
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
            var $zoneParent = $zoneSelect.closest('#zoneFilterCardShop, #products_grid_before, body');
            
            $zoneSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                placeholder: 'Buscar zona...',
                allowClear: false,
                dropdownParent: $zoneParent.length ? $zoneParent.first() : $('body'),
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
        
        // Focus en el campo de búsqueda al abrir
        $(document).on('select2:open', function(e) {
            setTimeout(function() {
                var searchField = document.querySelector('.select2-container--open .select2-search__field');
                if (searchField) {
                    searchField.focus();
                }
            }, 100);
        });
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShopSelect2);
    } else {
        initShopSelect2();
    }
    
    setTimeout(initShopSelect2, 1000);
    setTimeout(initShopSelect2, 2000);
})();
