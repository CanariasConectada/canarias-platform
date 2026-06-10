/* CANARIAS CONECTADA - OCULTAR CARRITO Y REDIRECCIONAR A MICROSITES */
/* Ejecutado inmediatamente - antes de que se pinte la pantalla */

(function() {
    'use strict';
    
    console.log('[Canarias FAST] ===== SCRIPT INICIADO =====');
    
    // Variables para control
    var isInitialized = false;
    var initAttempts = 0;
    var maxAttempts = 50; // Intentar durante ~5 segundos
    
    // Función principal - ejecutar lo antes posible
    function fastInit() {
        initAttempts++;
        
        if (isInitialized && initAttempts > 10) {
            return; // Ya inicializado después de varios intentos
        }
        
        // Verificar si hay productos en la página
        var productCards = document.querySelectorAll('.oe_product_cart');
        
        if (productCards.length === 0 && initAttempts < maxAttempts) {
            // No hay productos aún, reintentar
            requestAnimationFrame(fastInit);
            return;
        }
        
        console.log('[Canarias FAST] Productos encontrados:', productCards.length);
        
        // 1. Asegurar que el carrito esté oculto (CSS ya lo hizo, pero por si acaso)
        enforceCartHidden();
        
        // 2. Redireccionar imágenes y títulos a microsites
        redirectToMicrosites();
        
        isInitialized = true;
        console.log('[Canarias FAST] ===== INICIALIZACIÓN COMPLETA =====');
    }
    
    // Forzar ocultamiento del carrito (backup del CSS)
    function enforceCartHidden() {
        var elements = document.querySelectorAll(
            '.o_wsale_my_cart, ' +
            'a[href*="/shop/cart"], ' +
            '.fa-shopping-cart, ' +
            '.o_wsale_cart_quantity, ' +
            '.oe_product .o_wsale_product_btn, ' +
            '.oe_product .a-submit, ' +
            '.oe_product .o_add_cart_button'
        );
        
        elements.forEach(function(el) {
            el.style.cssText = 'display: none !important; visibility: hidden !important; opacity: 0 !important;';
        });
        
        console.log('[Canarias FAST] Elementos de carrito ocultados:', elements.length);
    }
    
    // Redireccionar a producto específico en microsite
    function redirectToMicrosites() {
        var productCards = document.querySelectorAll('.oe_product_cart');
        var redirectCount = 0;
        
        productCards.forEach(function(card) {
            var merchantDomain = card.getAttribute('data-merchant-domain');
            if (!merchantDomain) return;
            
            // Obtener el slug del producto del enlace actual
            var titleLink = card.querySelector('.o_wsale_products_item_title a');
            var productSlug = '';
            
            if (titleLink) {
                var currentHref = titleLink.getAttribute('href') || '';
                var match = currentHref.match(/\/shop\/(.+)$/);
                if (match) {
                    productSlug = match[1];
                }
            }
            
            // Construir URL completa al producto
            var cleanDomain = merchantDomain.replace(/\/$/, '');
            var productUrl = cleanDomain + '/shop/' + productSlug;
            
            // Aplicar redirección
            var imageLink = card.querySelector('a.oe_product_image_link');
            if (imageLink && imageLink.getAttribute('href') !== productUrl) {
                imageLink.setAttribute('href', productUrl);
                imageLink.setAttribute('target', '_blank');
                redirectCount++;
            }
            
            if (titleLink && titleLink.getAttribute('href') !== productUrl) {
                titleLink.setAttribute('href', productUrl);
                titleLink.setAttribute('target', '_blank');
            }
        });
        
        if (redirectCount > 0) {
            console.log('[Canarias FAST] Productos redireccionados:', redirectCount);
        }
    }
    
    // EJECUCIÓN INMEDIATA - antes de DOMContentLoaded si es posible
    if (document.readyState === 'loading') {
        // El DOM aún está cargando, ejecutar en cuanto sea posible
        document.addEventListener('readystatechange', function() {
            if (document.readyState === 'interactive' || document.readyState === 'complete') {
                fastInit();
            }
        });
        
        // Backup: DOMContentLoaded
        document.addEventListener('DOMContentLoaded', fastInit);
    } else {
        // El DOM ya está listo, ejecutar inmediatamente
        fastInit();
    }
    
    // EJECUCIÓN CONTINUA durante los primeros 3 segundos
    // Esto asegura que se aplique incluso con carga lazy
    var fastInterval = setInterval(function() {
        if (initAttempts >= maxAttempts) {
            clearInterval(fastInterval);
            return;
        }
        fastInit();
    }, 100);
    
    // Detener intervalo después de 3 segundos
    setTimeout(function() {
        clearInterval(fastInterval);
        console.log('[Canarias FAST] Intervalo detenido. Intentos totales:', initAttempts);
    }, 3000);
    
    // Re-ejecutar después de navegación AJAX
    if (window.jQuery) {
        jQuery(document).on('ajaxComplete', function() {
            isInitialized = false; // Forzar re-inicialización
            initAttempts = 0;
            fastInit();
        });
    }
    
    // Observar cambios en el DOM (nuevos productos cargados)
    var observer = new MutationObserver(function(mutations) {
        var hasNewProducts = false;
        mutations.forEach(function(mutation) {
            mutation.addedNodes.forEach(function(node) {
                if (node.nodeType === Node.ELEMENT_NODE) {
                    if (node.classList && node.classList.contains('oe_product_cart')) {
                        hasNewProducts = true;
                    } else if (node.querySelector && node.querySelector('.oe_product_cart')) {
                        hasNewProducts = true;
                    }
                }
            });
        });
        
        if (hasNewProducts) {
            fastInit();
        }
    });
    
    // Iniciar observador lo antes posible
    if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
    } else {
        document.addEventListener('DOMContentLoaded', function() {
            observer.observe(document.body, { childList: true, subtree: true });
        });
    }
    
    console.log('[Canarias FAST] ===== CONFIGURACIÓN COMPLETA =====');
})();
