/* Directory Select2 - Filtros con búsqueda */
odoo.define('website_directory.select2_filters', function (require) {
    'use strict';

    require('web.dom_ready');

    // Esperar a que Select2 esté disponible
    function initSelect2() {
        if (typeof $.fn.select2 === 'undefined') {
            // Select2 no cargado aún, esperar
            setTimeout(initSelect2, 100);
            return;
        }

        // Inicializar Select2 para Zonas
        var $zoneSelect = $('#zoneSelect');
        if ($zoneSelect.length && !$zoneSelect.hasClass('select2-hidden-accessible')) {
            $zoneSelect.select2({
                theme: 'bootstrap-5',
                width: '100%',
                minimumResultsForSearch: 0,
                allowClear: false
            }).on('change', function () {
                $(this).closest('form').submit();
            });
        }

        // Inicializar Select2 para Categorías
        var $catSelect = $('.directory-select2');
        $catSelect.each(function () {
            if (!$(this).hasClass('select2-hidden-accessible')) {
                $(this).select2({
                    theme: 'bootstrap-5',
                    width: '100%',
                    minimumResultsForSearch: 3,
                    allowClear: false
                });
            }
        });
    }

    // Iniciar cuando el DOM esté listo
    $(document).ready(function () {
        initSelect2();
    });
});
