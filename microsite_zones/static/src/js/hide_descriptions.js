/** @odoo-module **/

/**
 * Este script oculta las descripciones de productos en el listado de la tienda
 */
function hideProductDescriptions() {
    // Seleccionar todos los elementos de descripción
    const selectors = [
        '.oe_subdescription_wrapper',
        '.oe_subdescription',
        '.o_wsale_product_grid .text-muted.small',
        '#products_grid .oe_subdescription',
        '[t-field="product.description_sale"]',
        '.o_wsale_products_item .text-muted',
        '.o_wsale_product_information .text-muted',
        'div.text-muted.small',
    ];
    
    selectors.forEach(selector => {
        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
            el.style.display = 'none';
            el.style.visibility = 'hidden';
            el.style.height = '0';
            el.style.overflow = 'hidden';
            el.style.opacity = '0';
            el.classList.add('d-none');
        });
    });
}

// Ejecutar cuando el DOM esté listo
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', hideProductDescriptions);
} else {
    hideProductDescriptions();
}

// Ejecutar también después de que Odoo cargue los productos
setTimeout(hideProductDescriptions, 500);
setTimeout(hideProductDescriptions, 1000);
setTimeout(hideProductDescriptions, 2000);

// Observar cambios en el DOM para ocultar descripciones dinámicamente
const observer = new MutationObserver((mutations) => {
    hideProductDescriptions();
});

observer.observe(document.body, {
    childList: true,
    subtree: true
});

export default hideProductDescriptions;
