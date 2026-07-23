// Replicar estructura de navbar igual a canariasconectada.es
// + Reestructurar cards de certificación
(function() {
    'use strict';

    function cleanNavbar() {
        // ========================================
        // 1. LIMPIAR MENÚ PRINCIPAL (top_menu)
        // ========================================
        // Permitir: Inicio (/), Tienda (/shop), Comercios (/directorio), Zonas Comerciales (#) y submenús de zonas (https://...)
var allowedPaths = ['/', '/shop', '/directorio', '/event', '/memoria-viva', '/lugares-de-interes', '/resenas', '#'];

        ['#top_menu', '#top_menu_collapse_mobile'].forEach(function(selector) {
            var container = document.querySelector(selector);
            if (!container) return;

            container.querySelectorAll('li.nav-item').forEach(function(li) {
                var link = li.querySelector('a[role="menuitem"]');
                if (!link) return;

                var href = link.getAttribute('href') || '';

                // Permitir: /, /shop, /directorio, # (dropdown), y enlaces a zonas (canariasconectada.es)
                var isAllowed = allowedPaths.indexOf(href) !== -1 ||
                                href.indexOf('https://canariasconectada.es') === 0 ||
                                href.indexOf('https://guanarteme.canariasconectada.es') === 0 ||
                                href.indexOf('https://lomolosfrailes.canariasconectada.es') === 0 ||
                                href.indexOf('https://tamaraceite.canariasconectada.es') === 0;

                if (!isAllowed) {
                    li.style.display = 'none';
                }
            });

            // Manejar duplicados solo para paths simples, no para URLs de zonas
            ['/', '/shop', '/directorio'].forEach(function(path) {
                var seen = false;
                container.querySelectorAll('a[href="' + path + '"]').forEach(function(link) {
                    var li = link.closest('li');
                    if (!li) return;

                    if (seen) {
                        li.style.display = 'none';
                    } else {
                        seen = true;
                        li.style.display = '';
                    }
                });
            });
        });

        // ========================================
        // 2. OCULTAR ELEMENTOS NO DESEADOS
        // ========================================
        document.querySelectorAll('a[data-bs-target="#o_search_modal"]').forEach(function(el) {
            var li = el.closest('li');
            if (li) li.style.display = 'none';
        });

        document.querySelectorAll('a[href^="tel:"]').forEach(function(el) {
            var li = el.closest('li');
            if (li) li.style.display = 'none';
        });

        document.querySelectorAll('a[href*="contactus"].btn_cta').forEach(function(el) {
            var section = el.closest('.oe_structure');
            if (section) section.style.display = 'none';
        });

        // ========================================
        // 3. REESTRUCTURAR CARDS DE CERTIFICACIÓN
        // ========================================
        document.querySelectorAll('.s_company_team').forEach(function(section) {
            // Agregar margen inferior a la sección
            section.style.marginBottom = '40px';
            section.style.paddingBottom = '40px';

            var grid = section.querySelector('.o_grid');
            if (!grid) return;

            // Limpiar estilos inline del grid
            grid.style.gridTemplateColumns = '1fr';
            grid.style.justifyItems = 'center';

            // Procesar cards de Sostenible (con enlace exterior)
            grid.querySelectorAll(':scope > a[href*="sostenible"]').forEach(function(link) {
                var href = link.getAttribute('href');
                var gridItem = link.querySelector('.o_grid_item');
                var cardBody = link.querySelector('.card-body');

                if (gridItem && cardBody) {
                    // Limpiar estilos
                    gridItem.style.gridArea = 'auto';
                    gridItem.style.zIndex = '';

                    // Mover grid-item fuera del enlace
                    link.parentNode.insertBefore(gridItem, link);

                    // Verificar si ya tiene botón
                    if (!cardBody.querySelector('.btn-certificacion')) {
                        var btnDiv = document.createElement('div');
                        btnDiv.className = 'text-center';
                        btnDiv.style.marginTop = '15px';
                        btnDiv.innerHTML = '<a href="' + href + '" target="_blank" class="btn btn-primary btn-certificacion">Ver Sostenible</a>';
                        cardBody.appendChild(btnDiv);
                    }

                    link.remove();
                }
            });

            // Procesar cards de Silver Economy (sin enlace)
            grid.querySelectorAll(':scope > .o_grid_item').forEach(function(gridItem) {
                var cardBody = gridItem.querySelector('.card-body');
                var img = gridItem.querySelector('img');

                if (cardBody && img && img.src.includes('silver')) {
                    // Limpiar estilos
                    gridItem.style.gridArea = 'auto';
                    gridItem.style.zIndex = '';

                    // Verificar si ya tiene botón
                    if (!cardBody.querySelector('.btn-certificacion')) {
                        var btnDiv = document.createElement('div');
                        btnDiv.className = 'text-center';
                        btnDiv.style.marginTop = '15px';
                        btnDiv.innerHTML = '<a href="https://canariasconectada.es/silver-economy" target="_blank" class="btn btn-primary btn-certificacion">Ver Silver Economy</a>';
                        cardBody.appendChild(btnDiv);
                    }
                }
            });

            // Centrar imagen en todos los cards
            grid.querySelectorAll('.o_card_img_wrapper').forEach(function(wrapper) {
                wrapper.style.display = 'flex';
                wrapper.style.alignItems = 'center';
                wrapper.style.justifyContent = 'center';
                wrapper.style.minHeight = '200px';
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', cleanNavbar);
    } else {
        cleanNavbar();
    }

    setTimeout(cleanNavbar, 100);
    setTimeout(cleanNavbar, 500);
    setTimeout(cleanNavbar, 1000);
})();
