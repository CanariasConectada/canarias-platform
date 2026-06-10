/** @odoo-module **/

import publicWidget from "@web/legacy/js/public/public_widget";
import { rpc } from "@web/core/network/rpc";

/**
 * Widget para redirigir productos a sus microsites correspondientes
 * en Canarias Conectada y zonas comerciales
 */
publicWidget.registry.ProductMicrositeRedirect = publicWidget.Widget.extend({
    selector: '#o_wsale_products_grid',
    
    /**
     * Inicializa el widget
     */
    start: function () {
        const self = this;
        this._super.apply(this, arguments);
        
        // Verificar si estamos en Canarias Conectada o zona
        if (this._shouldRedirect()) {
            this._modifyProductLinks();
        }
    },

    /**
     * Modifica los links de productos para apuntar a sus microsites
     */
    _modifyProductLinks: function () {
        const self = this;
        
        // Buscar todos los links de productos
        this.$el.find('.oe_product_cart a, .oe_product a').each(function () {
            const $link = $(this);
            const href = $link.attr('href');
            
            // Si es un link de producto (contiene /shop/)
            if (href && href.startsWith('/shop/') && href !== '/shop/cart') {
                // Buscar el contenedor del producto para obtener data-company-id
                const $product = $link.closest('.oe_product_cart, .oe_product');
                const companyId = $product.attr('data-company-id');
                
                if (companyId) {
                    // Buscar la URL del microsite
                    const micrositeUrl = self._getMicrositeUrl(companyId, href);
                    if (micrositeUrl) {
                        $link.attr('href', micrositeUrl);
                        $link.attr('target', '_blank'); // Abrir en nueva pestaña
                    }
                }
            }
        });
    },

    /**
     * Determina si debe redirigir basado en el website actual
     */
    _shouldRedirect: function () {
        const body = document.body;
        const isCanarias = body.getAttribute('data-is-canarias') === 'True';
        const isZone = body.getAttribute('data-is-zone') === 'True';
        
        return isCanarias || isZone;
    },

    /**
     * Obtiene la URL del microsite basado en el company_id
     */
    _getMicrositeUrl: function (companyId, productPath) {
        // Mapa de company_id a dominios (se puede mejorar con una llamada al servidor)
        const companyDomains = {
            // Aquí se debería hacer una llamada al servidor para obtener los dominios
            // Por ahora, usamos un enfoque simple: el enlace permanece igual
            // pero se abre en nueva pestaña si viene de Canarias/zona
        };
        
        // Por ahora, solo abrimos en nueva pestaña
        // La URL real se generará en el servidor
        return null; // Retornamos null para mantener el comportamiento por defecto
    },
});

/**
 * Widget alternativo: Captura clics en productos y redirige
 */
publicWidget.registry.ProductClickRedirect = publicWidget.Widget.extend({
    selector: '.oe_website_sale',
    events: {
        'click .oe_product a[href^="/shop/"]': '_onProductClick',
    },

    /**
     * Maneja el clic en un producto
     */
    _onProductClick: function (ev) {
        const $link = $(ev.currentTarget);
        const href = $link.attr('href');
        
        // Ignorar el carrito
        if (href === '/shop/cart') {
            return;
        }
        
        // Verificar si estamos en Canarias Conectada o zona
        if (!this._shouldRedirect()) {
            return;
        }
        
        // Obtener el company_id del producto
        const $product = $link.closest('.oe_product_cart, .oe_product');
        const companyId = $product.attr('data-company-id');
        
        if (!companyId) {
            return;
        }
        
        // Prevenir navegación por defecto
        ev.preventDefault();
        
        // Hacer llamada al servidor para obtener la URL del microsite
        rpc('/shop/product/microsite_url', {
            company_id: parseInt(companyId),
            product_path: href,
        }).then(function (result) {
            if (result.url) {
                window.open(result.url, '_blank');
            } else {
                // Si no hay URL, navegar normalmente
                window.location.href = href;
            }
        }).catch(function () {
            // En caso de error, navegar normalmente
            window.location.href = href;
        });
    },

    /**
     * Determina si debe redirigir
     */
    _shouldRedirect: function () {
        const body = document.body;
        const isCanarias = body.getAttribute('data-is-canarias') === 'True';
        const isZone = body.getAttribute('data-is-zone') === 'True';
        return isCanarias || isZone;
    },
});

export default publicWidget.registry.ProductMicrositeRedirect;
