/* CANARIAS - OCULTAR CARRITO Y REDIRECCIONAR */
(function() {
    'use strict';
    
    function init() {
        // Ocultar carrito
        document.querySelectorAll('.o_wsale_my_cart, .o_wsale_product_btn').forEach(function(el) {
            el.style.display = 'none !important';
        });
        
        // Redireccionar productos
        document.querySelectorAll('.oe_product_cart[data-merchant-domain]').forEach(function(card) {
            var domain = card.getAttribute('data-merchant-domain');
            if(!domain) return;
            var titleLink = card.querySelector('.o_wsale_products_item_title a');
            var imgLink = card.querySelector('a.oe_product_image_link');
            if(titleLink) {
                var href = titleLink.getAttribute('href') || '';
                var match = href.match(/\/shop\/(.+)$/);
                var slug = match ? match[1] : '';
                var url = domain.replace(/\/$/, '') + '/shop/' + slug;
                titleLink.href = url;
                titleLink.target = '_blank';
                if(imgLink) {
                    imgLink.href = url;
                    imgLink.target = '_blank';
                }
            }
        });
    }
    
    if(document.readyState !== 'loading') init();
    document.addEventListener('DOMContentLoaded', init);
    if(window.jQuery) jQuery(document).on('ajaxComplete', function(){ setTimeout(init, 100); });
})();
