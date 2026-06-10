// Bootstrap-Select para filtros de la tienda (/shop)
// Solución: container: 'body' para evitar problemas de overflow
// Documentación: https://developer.snapappointments.com/bootstrap-select/options/

(function() {
    'use strict';
    
    function initBootstrapSelect() {
        if (!window.location.pathname.startsWith('/shop')) {
            return;
        }
        
        if (typeof jQuery === 'undefined') {
            setTimeout(initBootstrapSelect, 200);
            return;
        }
        
        var $ = jQuery;
        
        if (typeof $.fn.selectpicker === 'undefined') {
            loadBootstrapSelect($).then(function() {
                initializeSelects($);
            }).catch(function() {
                console.log('[BootstrapSelect] No se pudo cargar');
            });
        } else {
            initializeSelects($);
        }
    }
    
    function loadBootstrapSelect($) {
        return new Promise(function(resolve, reject) {
            if (!$('link[href*="bootstrap-select"]').length) {
                $('<link>')
                    .attr('rel', 'stylesheet')
                    .attr('href', 'https://cdn.jsdelivr.net/npm/bootstrap-select@1.14.0-beta3/dist/css/bootstrap-select.min.css')
                    .appendTo('head');
            }
            
            $.getScript('https://cdn.jsdelivr.net/npm/bootstrap-select@1.14.0-beta3/dist/js/bootstrap-select.min.js')
                .done(function() {
                    resolve();
                })
                .fail(function() {
                    reject();
                });
        });
    }
    
    function initializeSelects($) {
        // Categorías - Con container: 'body' para evitar overflow
        var $catSelect = $('#category-select-shop');
        if ($catSelect.length && !$catSelect.hasClass('selectpicker')) {
            $catSelect.selectpicker({
                style: 'btn-outline-secondary',
                size: 10,
                liveSearch: true,
                liveSearchPlaceholder: 'Buscar categoría...',
                noneSelectedText: 'Todas las categorías',
                dropupAuto: false,
                width: '100%',
                container: 'body'  // <-- SOLUCIÓN: Renderizar en body
            });
            
            $catSelect.on('changed.bs.select', function(e) {
                var url = $(this).val();
                if (url && url !== window.location.href) {
                    window.location.href = url;
                }
            });
        }
        
        // Subcategorías
        var $subCatSelect = $('#subcategory-select-shop');
        if ($subCatSelect.length && !$subCatSelect.hasClass('selectpicker')) {
            $subCatSelect.selectpicker({
                style: 'btn-outline-secondary',
                size: 10,
                liveSearch: true,
                liveSearchPlaceholder: 'Buscar subcategoría...',
                noneSelectedText: 'Todas las subcategorías',
                dropupAuto: false,
                width: '100%',
                container: 'body'  // <-- SOLUCIÓN: Renderizar en body
            });
            
            $subCatSelect.on('changed.bs.select', function(e) {
                var url = $(this).val();
                if (url && url !== window.location.href) {
                    window.location.href = url;
                }
            });
        }
    }
    
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initBootstrapSelect);
    } else {
        initBootstrapSelect();
    }
    
    setTimeout(initBootstrapSelect, 1000);
    setTimeout(initBootstrapSelect, 2000);
})();
